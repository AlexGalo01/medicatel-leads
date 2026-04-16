from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from langsmith import traceable

from mle.clients.exa_client import ExaClient
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.core.config import get_settings
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _build_search_payload(planner_output: dict[str, Any]) -> dict[str, Any]:
    search_config = planner_output.get("search_config", {})
    query = str(search_config.get("query", "")).strip()
    search_type = str(search_config.get("type", "auto")).strip() or "auto"
    num_results = int(search_config.get("num_results", 25))
    use_highlights = bool(search_config.get("use_highlights", True))
    include_domains = list(search_config.get("include_domains", []))
    exclude_domains = list(search_config.get("exclude_domains", []))

    payload: dict[str, Any] = {
        "query": query,
        "type": search_type,
        "numResults": num_results,
    }
    if use_highlights:
        payload["contents"] = {
            "highlights": {
                "maxCharacters": 5000,
                "query": "extrae correos electronicos, whatsapp, telefonos y datos de contacto verificables",
            }
        }
    if include_domains:
        payload["includeDomains"] = include_domains
    if exclude_domains:
        payload["excludeDomains"] = exclude_domains
    return payload


def _ensure_non_empty_query(payload: dict[str, Any], fallback_query: str) -> dict[str, Any]:
    query = str(payload.get("query", "")).strip()
    if query:
        return payload

    normalized_fallback = " ".join(fallback_query.strip().split())
    if not normalized_fallback:
        return payload

    payload["query"] = normalized_fallback
    return payload


def _extract_results(search_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = search_response.get("results", [])
    if isinstance(raw_results, list):
        return [result for result in raw_results if isinstance(result, dict)]
    return []


@traceable(
    name="exa_webset_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def exa_webset_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Execute Exa search using planner output and return state patch.

    Node keeps graceful-failure behavior and never raises outside.
    """
    try:
        planner_output = state.planner_output
        if not planner_output:
            raise ValueError("No existe planner_output para ejecutar Exa Search.")

        payload = _build_search_payload(planner_output)
        payload = _ensure_non_empty_query(payload, fallback_query=state.query_text)

        if not str(payload.get("query", "")).strip():
            raise ValueError("El query tecnico de Exa esta vacio.")

        settings = get_settings()
        exa_client = ExaClient(api_key=settings.exa_api_key)

        await asyncio.sleep(0)
        search_response = await exa_client.search(payload)
        exa_results = _extract_results(search_response)
        search_type = str(search_response.get("searchType", payload.get("type", "auto")))
        request_id = str(search_response.get("requestId", ""))

        logger.info(
            "Exa search node completado para job_id=%s con %s resultados",
            state.job_id,
            len(exa_results),
        )

        return {
            "status": "running",
            "current_stage": "scoring_cleaning",
            "progress": 60,
            "exa_raw_results": exa_results,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "exa_payload": payload,
                "search_type": search_type,
                "request_id": request_id,
                "results_count": len(exa_results),
            },
        }
    except Exception as exc:  # noqa: BLE001 - graceful pipeline behavior
        error_message = f"Exa search node fallo: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "error",
            "current_stage": "exa_search",
            "progress": state.progress,
            "exa_raw_results": [],
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "exa_error": error_message,
                "exa_state_snapshot": asdict(state),
            },
        }

