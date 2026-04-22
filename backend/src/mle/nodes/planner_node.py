from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

from langsmith import traceable

from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.core.config import get_settings
from mle.schemas.planner import ExaSearchConfig, PlannerOutput, RelevanceCriteria
from mle.services.country_iso_resolution import resolve_country_iso2_from_text
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)

ALLOWED_CONTACT_CHANNELS: set[str] = {"email", "whatsapp", "linkedin"}


def _normalize_text(raw_text: str) -> str:
    return " ".join(raw_text.strip().split())


def _extract_contact_channels(query_text: str) -> list[str]:
    normalized_query = query_text.lower()
    detected_channels: list[str] = []

    if "email" in normalized_query or "correo" in normalized_query:
        detected_channels.append("email")
    if "whatsapp" in normalized_query or "telefono" in normalized_query:
        detected_channels.append("whatsapp")
    if "linkedin" in normalized_query:
        detected_channels.append("linkedin")

    if not detected_channels:
        return ["email", "whatsapp", "linkedin"]

    unique_channels = sorted(set(detected_channels))
    return [channel for channel in unique_channels if channel in ALLOWED_CONTACT_CHANNELS]


def _build_exa_query(query_text: str) -> str:
    return _normalize_text(query_text)


def _build_planner_output(state: LeadSearchGraphState) -> PlannerOutput:
    normalized_query = _normalize_text(state.query_text)
    if not normalized_query:
        raise ValueError("El query normalizado quedo vacio.")

    channels = _extract_contact_channels(normalized_query)
    plan_dict = state.search_plan if isinstance(state.search_plan, dict) else {}
    main_from_plan = str(plan_dict.get("main_query", "")).strip()
    base_query = main_from_plan or _build_exa_query(normalized_query)
    if len(base_query.strip()) < 3:
        base_query = _build_exa_query(normalized_query)

    additional_raw = plan_dict.get("additional_queries", [])
    additional_clean: list[str] = []
    if isinstance(additional_raw, list):
        for item in additional_raw:
            text = str(item).strip()
            if not text or text.lower() == base_query.lower():
                continue
            if text not in additional_clean:
                additional_clean.append(text[:400])

    exa_cat = plan_dict.get("exa_category")
    if exa_cat not in ("people", "company", None):
        exa_cat = None
    if exa_cat == "":
        exa_cat = None
    if exa_cat is None:
        exa_cat = "people"

    search_config = ExaSearchConfig(
        query=base_query,
        type=get_settings().exa_search_type,
        num_results=50,
        use_highlights=True,
        additional_queries=additional_clean[:8],
        exa_category=exa_cat,
    )

    entity_hint = str(plan_dict.get("entity_type", "")).strip()
    geo = plan_dict.get("geo") if isinstance(plan_dict.get("geo"), dict) else {}
    city_hint = str(geo.get("city", "")).strip() if geo else ""
    country_hint = str(geo.get("country", "")).strip() if geo else ""
    normalized_specialty = entity_hint or normalized_query
    normalized_location = ", ".join(p for p in (city_hint, country_hint) if p) or "No definida"
    planner_notes = "Plan de directorio: query principal y variaciones para Exa."

    country_iso2 = resolve_country_iso2_from_text(country_hint, city_hint, normalized_query)
    relevance_criteria = RelevanceCriteria(
        country_iso2=country_iso2,
        city=city_hint or None,
        country_text=country_hint or None,
        role_or_stack_hint=(entity_hint or normalized_query)[:400] or None,
        normalized_location=None if normalized_location == "No definida" else normalized_location,
    )

    return PlannerOutput(
        search_config=search_config,
        normalized_specialty=normalized_specialty,
        normalized_location=normalized_location,
        relevance_criteria=relevance_criteria,
        contact_channels=channels,
        planner_notes=planner_notes,
    )


@traceable(
    name="planner_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def planner_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Build technical Exa search configuration from plain user query.

    Returns a state patch compatible with LangGraph node-function pattern.
    """
    try:
        if not state.query_text.strip():
            raise ValueError("El query de entrada esta vacio.")

        # Async boundary to keep node non-blocking and future-proof.
        await asyncio.sleep(0)
        planner_output = _build_planner_output(state)

        logger.info("Planner node completado para job_id=%s", state.job_id)
        return {
            "status": "running",
            "current_stage": "exa_webset",
            "progress": 20,
            "planner_output": planner_output.model_dump(),
        }
    except Exception as exc:  # noqa: BLE001 - explicit graceful handling per plan
        error_message = f"Planner node fallo: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "error",
            "current_stage": "planner",
            "progress": state.progress,
            "planner_output": {},
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "planner_error": error_message,
                "planner_state_snapshot": asdict(state),
            },
        }

