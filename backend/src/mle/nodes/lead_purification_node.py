from __future__ import annotations

import logging
import re
from dataclasses import asdict
from typing import Any

from langsmith import traceable

from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.state.graph_state import GraphLeadItem, LeadSearchGraphState

logger = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"[+\d][\d\s\-()]{7,}")


def _normalize_email(raw_email: str | None) -> str | None:
    normalized = str(raw_email or "").strip().lower()
    if not normalized:
        return None
    if not EMAIL_PATTERN.match(normalized):
        return None
    return normalized


def _normalize_whatsapp(raw_value: str | None) -> str | None:
    normalized = str(raw_value or "").strip()
    if not normalized:
        return None
    if not PHONE_PATTERN.search(normalized):
        return None
    digits = re.sub(r"\D+", "", normalized)
    if len(digits) < 8:
        return None
    if normalized.startswith("+"):
        return f"+{digits}"
    return digits


def _normalize_url(raw_value: str | None) -> str | None:
    normalized = str(raw_value or "").strip()
    if not normalized:
        return None
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    return None


def _lead_contact_key(lead_item: GraphLeadItem) -> str:
    return "|".join(
        [
            lead_item.email or "",
            lead_item.whatsapp or "",
            lead_item.linkedin_url or "",
            lead_item.full_name.strip().lower(),
        ]
    )


def _is_valid_lead(lead_item: GraphLeadItem) -> bool:
    return bool(lead_item.email or lead_item.whatsapp)


def _is_partial_lead(lead_item: GraphLeadItem) -> bool:
    return bool(lead_item.linkedin_url and lead_item.source_citations)


@traceable(
    name="lead_purification_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def lead_purification_node(state: LeadSearchGraphState) -> dict[str, object]:
    """Normalize, validate and deduplicate leads before persistence."""
    try:
        normalized_leads: list[dict[str, Any]] = []
        discarded_leads: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        for lead_payload in state.leads:
            if isinstance(lead_payload, dict):
                lead_item = GraphLeadItem(**lead_payload)
            elif isinstance(lead_payload, GraphLeadItem):
                lead_item = lead_payload
            else:
                continue

            lead_item.email = _normalize_email(lead_item.email)
            lead_item.whatsapp = _normalize_whatsapp(lead_item.whatsapp)
            lead_item.linkedin_url = _normalize_url(lead_item.linkedin_url)
            lead_item.full_name = str(lead_item.full_name or "").strip() or "Lead sin nombre"

            dedup_key = _lead_contact_key(lead_item)
            if dedup_key in seen_keys:
                discarded_leads.append(
                    {
                        "full_name": lead_item.full_name,
                        "discard_reason": "duplicate",
                    }
                )
                continue
            seen_keys.add(dedup_key)

            if _is_valid_lead(lead_item):
                normalized_leads.append({**asdict(lead_item), "purification_status": "valid"})
                continue

            if _is_partial_lead(lead_item):
                normalized_leads.append({**asdict(lead_item), "purification_status": "partial"})
                continue

            discarded_leads.append(
                {
                    "full_name": lead_item.full_name,
                    "discard_reason": "invalid_contact_data",
                }
            )

        total_candidates = len(normalized_leads) + len(discarded_leads)
        valid_contact_count = sum(
            1 for lead in normalized_leads if lead.get("email") or lead.get("whatsapp")
        )
        contact_coverage = valid_contact_count / total_candidates if total_candidates else 0.0
        missing_contact_count = len(
            [lead for lead in normalized_leads if not lead.get("email") and not lead.get("whatsapp")]
        )

        logger.info(
            "Lead purification completada job_id=%s total=%s retained=%s discarded=%s",
            state.job_id,
            total_candidates,
            len(normalized_leads),
            len(discarded_leads),
        )
        return {
            "status": "running",
            "current_stage": "contact_retry",
            "progress": 92,
            "leads": normalized_leads,
            "discarded_leads": discarded_leads,
            "contact_coverage": contact_coverage,
            "missing_contact_count": missing_contact_count,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "purification": {
                    "total_candidates": total_candidates,
                    "retained": len(normalized_leads),
                    "discarded": len(discarded_leads),
                    "contact_coverage": round(contact_coverage, 4),
                    "missing_contact_count": missing_contact_count,
                },
            },
        }
    except Exception as exc:  # noqa: BLE001
        error_message = f"Lead purification node fallo: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "error",
            "current_stage": "lead_purification",
            "progress": state.progress,
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "purification_error": error_message,
            },
        }
