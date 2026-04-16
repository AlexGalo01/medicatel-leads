from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

from langsmith import traceable

from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.schemas.planner import ExaSearchConfig, PlannerOutput
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
    exa_query = _build_exa_query(normalized_query)

    search_config = ExaSearchConfig(
        query=exa_query,
        type="deep",
        num_results=100,
        use_highlights=True,
    )

    normalized_specialty = normalized_query
    normalized_location = "No definida"
    planner_notes = "Busqueda general configurada con estrategia search profunda."

    return PlannerOutput(
        search_config=search_config,
        normalized_specialty=normalized_specialty,
        normalized_location=normalized_location,
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

