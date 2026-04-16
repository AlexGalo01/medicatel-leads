from __future__ import annotations

import logging
import re
from typing import Any

from langsmith import traceable

from mle.clients.exa_client import ExaClient
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.core.config import get_settings
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)

CONTACT_COVERAGE_THRESHOLD = 0.35
EMAIL_SNIPPET_PATTERN = re.compile(r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.IGNORECASE)
PHONE_SNIPPET_PATTERN = re.compile(r"(\+?\d[\d\s\-()]{7,}\d)")


def _build_retry_payload(state: LeadSearchGraphState) -> dict[str, Any]:
    planner_output = state.planner_output
    search_config = planner_output.get("search_config", {}) if isinstance(planner_output, dict) else {}
    base_query = str(search_config.get("query", state.query_text)).strip() or state.query_text
    retry_query = (
        f"{base_query} incluir correo electronico y whatsapp "
        "site:linkedin.com OR contacto OR telefono OR email"
    )
    return {
        "query": retry_query,
        "type": "deep",
        "numResults": 100,
        "contents": {
            "highlights": {
                "maxCharacters": 5000,
                "query": "obtener email, whatsapp, telefono, contacto y canal directo",
            }
        },
    }


def _extract_highlight_text(result_item: dict[str, Any]) -> str:
    highlights = result_item.get("highlights", [])
    if isinstance(highlights, list):
        return " ".join(str(item) for item in highlights if item)
    text_value = result_item.get("text")
    return str(text_value or "")


def _extract_email(text_blob: str) -> str | None:
    match = EMAIL_SNIPPET_PATTERN.search(text_blob)
    return match.group(1).lower() if match else None


def _extract_phone(text_blob: str) -> str | None:
    match = PHONE_SNIPPET_PATTERN.search(text_blob)
    if not match:
        return None
    digits = re.sub(r"\D+", "", match.group(1))
    if len(digits) < 8:
        return None
    return f"+{digits}" if match.group(1).strip().startswith("+") else digits


def _merge_leads(existing_leads: list[dict[str, Any]], retry_leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for lead_item in [*existing_leads, *retry_leads]:
        dedup_key = "|".join(
            [
                str(lead_item.get("email", "") or "").lower(),
                str(lead_item.get("whatsapp", "") or ""),
                str(lead_item.get("linkedin_url", "") or ""),
                str(lead_item.get("full_name", "") or "").strip().lower(),
            ]
        )
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        merged.append(lead_item)
    return merged


@traceable(
    name="contact_retry_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def contact_retry_node(state: LeadSearchGraphState) -> dict[str, object]:
    """Run one retry search when contact coverage is below threshold."""
    try:
        if state.retry_used or state.contact_coverage >= CONTACT_COVERAGE_THRESHOLD:
            return {
                "status": "running",
                "current_stage": "storage_export",
                "progress": 95,
            }

        settings = get_settings()
        exa_client = ExaClient(api_key=settings.exa_api_key)
        retry_payload = _build_retry_payload(state)
        retry_response = await exa_client.search(retry_payload)
        retry_results = retry_response.get("results", [])
        if not isinstance(retry_results, list):
            retry_results = []

        retry_leads: list[dict[str, Any]] = []
        for result_item in retry_results:
            if not isinstance(result_item, dict):
                continue
            title = str(result_item.get("title", "")).strip() or "Lead sin nombre"
            url = str(result_item.get("url", "")).strip()
            highlight_text = _extract_highlight_text(result_item)
            retry_leads.append(
                {
                    "full_name": title,
                    "specialty": "Medicina general",
                    "city": "No definido",
                    "country": "Honduras",
                    "score": 5.5,
                    "score_reasoning": "Lead enriquecido por reintento de contacto.",
                    "email": _extract_email(highlight_text),
                    "whatsapp": _extract_phone(highlight_text),
                    "linkedin_url": url if "linkedin.com" in url else None,
                    "source_citations": [{"url": url, "title": title, "confidence": "medium"}]
                    if url
                    else [],
                    "purification_status": "valid",
                }
            )

        merged_leads = _merge_leads(state.leads, retry_leads)
        valid_contact_count = sum(
            1 for lead_item in merged_leads if lead_item.get("email") or lead_item.get("whatsapp")
        )
        updated_coverage = valid_contact_count / len(merged_leads) if merged_leads else 0.0
        missing_contact_count = len(
            [lead_item for lead_item in merged_leads if not lead_item.get("email") and not lead_item.get("whatsapp")]
        )

        logger.info(
            "Contact retry ejecutado job_id=%s retry_results=%s merged_leads=%s",
            state.job_id,
            len(retry_leads),
            len(merged_leads),
        )
        return {
            "status": "running",
            "current_stage": "storage_export",
            "progress": 96,
            "leads": merged_leads,
            "retry_used": True,
            "contact_coverage": updated_coverage,
            "missing_contact_count": missing_contact_count,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "contact_retry": {
                    "retry_used": True,
                    "retry_results": len(retry_leads),
                    "coverage_after_retry": round(updated_coverage, 4),
                },
            },
        }
    except Exception as exc:  # noqa: BLE001
        error_message = f"Contact retry node fallo: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "error",
            "current_stage": "contact_retry",
            "progress": state.progress,
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "contact_retry_error": error_message,
            },
        }
