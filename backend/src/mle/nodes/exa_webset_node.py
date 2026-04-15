from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from mle.clients.exa_client import ExaClient
from mle.core.config import get_settings
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)
WEBSET_POLL_MAX_ATTEMPTS = 20
WEBSET_POLL_INTERVAL_SECONDS = 2.0


def _build_webset_payload(planner_output: dict[str, Any]) -> dict[str, Any]:
    search_config = planner_output.get("search_config", {})
    query = str(search_config.get("query", "")).strip()
    num_results = int(search_config.get("num_results", 25))
    use_highlights = bool(search_config.get("use_highlights", True))
    include_domains = list(search_config.get("include_domains", []))
    exclude_domains = list(search_config.get("exclude_domains", []))

    search_payload: dict[str, Any] = {
        "query": query,
        "count": num_results,
    }
    if include_domains:
        search_payload["includeDomains"] = include_domains
    if exclude_domains:
        search_payload["excludeDomains"] = exclude_domains

    payload: dict[str, Any] = {"search": search_payload}
    if use_highlights:
        payload["enrichments"] = [
            {
                "description": "Extract the most relevant highlights for this result",
                "format": "text",
            }
        ]
    return payload


def _extract_results(webset_response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = webset_response.get("items", webset_response.get("results", []))
    if isinstance(raw_results, list):
        return [result for result in raw_results if isinstance(result, dict)]
    return []


def _extract_webset_id(create_response: dict[str, Any]) -> str:
    webset_id = (
        create_response.get("id")
        or create_response.get("websetId")
        or create_response.get("webset_id")
    )
    if not isinstance(webset_id, str) or not webset_id.strip():
        raise ValueError("Exa no devolvio webset_id valido.")
    return webset_id


def _extract_webset_status(webset_response: dict[str, Any]) -> str:
    status = webset_response.get("status", "unknown")
    return str(status).strip().lower()


async def exa_webset_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Execute Exa search using planner output and return state patch.

    Node keeps graceful-failure behavior and never raises outside.
    """
    try:
        planner_output = state.planner_output
        if not planner_output:
            raise ValueError("No existe planner_output para ejecutar Exa Webset.")

        payload = _build_webset_payload(planner_output)
        if not payload.get("query"):
            raise ValueError("El query tecnico de Exa esta vacio.")

        settings = get_settings()
        exa_client = ExaClient(api_key=settings.exa_api_key)

        create_response = await exa_client.create_webset(payload)
        webset_id = _extract_webset_id(create_response)

        webset_status = "created"
        poll_attempts = 0
        webset_response: dict[str, Any] = {}
        while poll_attempts < WEBSET_POLL_MAX_ATTEMPTS:
            poll_attempts += 1
            await asyncio.sleep(WEBSET_POLL_INTERVAL_SECONDS)
            webset_response = await exa_client.get_webset(webset_id, expand_items=False)
            webset_status = _extract_webset_status(webset_response)
            if webset_status in {"completed", "done", "ready", "success"}:
                break
            if webset_status in {"error", "failed", "cancelled", "canceled"}:
                raise ValueError(f"WebSet finalizo con estado invalido: {webset_status}")

        if webset_status not in {"completed", "done", "ready", "success"}:
            raise TimeoutError("WebSet no completo dentro del tiempo de polling.")

        exa_results = await exa_client.list_webset_items(webset_id=webset_id, limit=200)
        if not exa_results:
            expanded_response = await exa_client.get_webset(webset_id, expand_items=True)
            exa_results = _extract_results(expanded_response)

        logger.info(
            "Exa webset node completado para job_id=%s con %s resultados usando webset_id=%s",
            state.job_id,
            len(exa_results),
            webset_id,
        )

        return {
            "status": "running",
            "current_stage": "scoring_cleaning",
            "progress": 60,
            "webset_id": webset_id,
            "webset_status": webset_status,
            "webset_poll_attempts": poll_attempts,
            "exa_raw_results": exa_results,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "webset_payload": payload,
                "webset_id": webset_id,
                "webset_status": webset_status,
                "webset_poll_attempts": poll_attempts,
                "results_count": len(exa_results),
            },
        }
    except Exception as exc:  # noqa: BLE001 - graceful pipeline behavior
        error_message = f"Exa webset node fallo: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "error",
            "current_stage": "exa_webset",
            "progress": state.progress,
            "webset_id": state.webset_id,
            "webset_status": state.webset_status,
            "webset_poll_attempts": state.webset_poll_attempts,
            "exa_raw_results": [],
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "webset_error": error_message,
                "webset_state_snapshot": asdict(state),
            },
        }

