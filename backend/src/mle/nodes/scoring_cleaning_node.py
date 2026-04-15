from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from mle.clients.gemini_client import GeminiClient
from mle.core.config import get_settings
from mle.state.graph_state import GraphLeadItem, LeadSearchGraphState

logger = logging.getLogger(__name__)


def _extract_text(result: dict[str, Any], path: list[str]) -> str:
    current_value: Any = result
    for key in path:
        if not isinstance(current_value, dict):
            return ""
        current_value = current_value.get(key, "")
    return str(current_value).strip()


def _build_raw_lead(result: dict[str, Any]) -> GraphLeadItem:
    title = str(result.get("title", "")).strip()
    url = str(result.get("url", "")).strip()
    snippet = _extract_text(result, ["highlights", "0"])
    if not snippet:
        snippet = _extract_text(result, ["text"])

    full_name = title or "Lead sin nombre"
    specialty = "Medicina general"
    city = "No definido"
    country = "Honduras"

    return GraphLeadItem(
        full_name=full_name,
        specialty=specialty,
        city=city,
        country=country,
        email=_extract_text(result, ["email"]) or None,
        whatsapp=_extract_text(result, ["phone"]) or None,
        linkedin_url=url if "linkedin.com" in url else None,
        source_citations=[{"url": url, "title": title or "Fuente", "confidence": "medium"}] if url else [],
        score_reasoning=snippet or None,
    )


async def _score_with_gemini(gemini_client: GeminiClient, lead: GraphLeadItem) -> tuple[float, str]:
    lead_payload = {
        "full_name": lead.full_name,
        "specialty": lead.specialty,
        "city": lead.city,
        "country": lead.country,
        "email": lead.email,
        "whatsapp": lead.whatsapp,
        "linkedin_url": lead.linkedin_url,
        "context": lead.score_reasoning,
    }
    score_response = await gemini_client.score_lead(lead_payload)
    return float(score_response["score"]), str(score_response["reasoning"])


def _score_heuristic(lead: GraphLeadItem) -> tuple[float, str]:
    base_score = 4.0
    if lead.email:
        base_score += 2.0
    if lead.whatsapp:
        base_score += 2.0
    if lead.linkedin_url:
        base_score += 1.5
    if lead.source_citations:
        base_score += 0.5
    final_score = min(base_score, 10.0)
    reasoning = "Score calculado por heuristica debido a fallback local."
    return final_score, reasoning


async def scoring_cleaning_node(state: LeadSearchGraphState) -> dict[str, object]:
    """Clean Exa results and assign a lead score."""
    try:
        if not state.exa_raw_results:
            raise ValueError("No hay resultados de Exa para procesar.")

        settings = get_settings()
        gemini_client = GeminiClient(
            api_key=settings.google_api_key,
            model_name=settings.google_model,
        )

        cleaned_leads: list[GraphLeadItem] = []
        for raw_result in state.exa_raw_results:
            lead = _build_raw_lead(raw_result)
            try:
                # Async boundary to keep processing friendly for future batching.
                await asyncio.sleep(0)
                score, reasoning = await _score_with_gemini(gemini_client, lead)
            except Exception as gemini_error:  # noqa: BLE001
                logger.warning("Gemini no disponible para lead '%s': %s", lead.full_name, gemini_error)
                score, reasoning = _score_heuristic(lead)

            lead.score = score
            lead.score_reasoning = reasoning
            cleaned_leads.append(lead)

        serialized_leads = [asdict(lead_item) for lead_item in cleaned_leads]
        logger.info(
            "Scoring cleaning node completado para job_id=%s con %s leads",
            state.job_id,
            len(serialized_leads),
        )
        return {
            "status": "completed",
            "current_stage": "storage_export",
            "progress": 90,
            "leads": serialized_leads,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "cleaned_leads_count": len(serialized_leads),
            },
        }
    except Exception as exc:  # noqa: BLE001 - graceful pipeline behavior
        error_message = f"Scoring cleaning node fallo: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "error",
            "current_stage": "scoring_cleaning",
            "progress": state.progress,
            "leads": [],
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "scoring_error": error_message,
                "scoring_state_snapshot": asdict(state),
            },
        }

