from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from mle.clients.exa_client import ExaClient
from mle.core.config import get_settings
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _build_exa_payload(planner_output: dict[str, Any]) -> dict[str, Any]:
    search_config = planner_output.get("search_config", {})
    query = str(search_config.get("query", "")).strip()
    search_type = str(search_config.get("type", "deep")).strip() or "deep"
    num_results = int(search_config.get("num_results", 25))
    use_highlights = bool(search_config.get("use_highlights", True))

    payload: dict[str, Any] = {
        "query": query,
        "type": search_type,
        "num_results": num_results,
    }
    if use_highlights:
        payload["contents"] = {"highlights": {"max_characters": 4000}}
    return payload


def _extract_results(exa_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = exa_response.get("results", [])
    if isinstance(raw_results, list):
        return [result for result in raw_results if isinstance(result, dict)]
    return []


async def exa_webset_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Execute Exa search using planner output and return state patch.

    Node keeps graceful-failure behavior and never raises outside.
    """
    try:
        planner_output = state.planner_output
        if not planner_output:
            raise ValueError("No existe planner_output para ejecutar Exa Webset.")

        payload = _build_exa_payload(planner_output)
        if not payload.get("query"):
            raise ValueError("El query tecnico de Exa esta vacio.")

        settings = get_settings()
        exa_client = ExaClient(api_key=settings.exa_api_key)

        # Allow future polling expansion without blocking event loop.
        await asyncio.sleep(0)
        exa_response = await exa_client.search(payload)
        exa_results = _extract_results(exa_response)

        logger.info(
            "Exa webset node completado para job_id=%s con %s resultados",
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
                "exa_result_count": len(exa_results),
            },
        }
    except Exception as exc:  # noqa: BLE001 - graceful pipeline behavior
        error_message = f"Exa webset node fallo: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "error",
            "current_stage": "exa_webset",
            "progress": state.progress,
            "exa_raw_results": [],
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "exa_error": error_message,
                "exa_state_snapshot": asdict(state),
            },
        }

