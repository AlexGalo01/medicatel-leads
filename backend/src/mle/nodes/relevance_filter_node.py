from __future__ import annotations

import asyncio
import logging
from typing import Any

from langsmith import traceable

from mle.core.config import get_settings
from mle.clients.llm_factory import get_llm_client
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.services.relevance_filter_service import filter_exa_raw_results_by_relevance
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


@traceable(
    name="relevance_filter_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def relevance_filter_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Filtra resultados Exa que no cumplen criterios de ubicación / intención antes del enriquecimiento.
    """
    raw = [x for x in state.exa_raw_results if isinstance(x, dict)]
    try:
        await asyncio.sleep(0)
        if not raw:
            return {
                "status": "running",
                "current_stage": "search_finalize",
                "progress": 72,
                "exa_raw_results": [],
                "langsmith_metadata": {
                    **state.langsmith_metadata,
                    "relevance_filter_kept": 0,
                    "relevance_filter_dropped": 0,
                    "relevance_filter_mode": "skipped_empty",
                },
            }

        planner_output = state.planner_output if isinstance(state.planner_output, dict) else {}
        rel = planner_output.get("relevance_criteria") if isinstance(planner_output.get("relevance_criteria"), dict) else {}
        rel = dict(rel)
        rel.setdefault("normalized_location", str(planner_output.get("normalized_location") or ""))
        search_config = planner_output.get("search_config") if isinstance(planner_output.get("search_config"), dict) else {}
        exa_cat = search_config.get("exa_category")
        if exa_cat in ("people", "company"):
            rel["exa_category"] = exa_cat

        settings = get_settings()
        llm = get_llm_client(settings)

        filtered, meta = await filter_exa_raw_results_by_relevance(
            raw_results=raw,
            user_query=state.query_text,
            relevance_criteria=rel,
            gemini_client=llm,
        )

        logger.info(
            "relevance_filter job_id=%s kept=%s dropped=%s heuristic=%s",
            state.job_id,
            meta.get("relevance_filter_kept"),
            meta.get("relevance_filter_dropped"),
            meta.get("relevance_filter_heuristic_drops"),
        )

        return {
            "status": "running",
            "current_stage": "search_finalize",
            "progress": 72,
            "exa_raw_results": filtered,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                **meta,
            },
        }
    except Exception as exc:  # noqa: BLE001
        error_message = f"relevance_filter_node degradado: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "running",
            "current_stage": "search_finalize",
            "progress": 72,
            "exa_raw_results": raw,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "relevance_filter_kept": len(raw),
                "relevance_filter_dropped": 0,
                "relevance_filter_mode": "degraded_exception",
                "relevance_filter_error": error_message,
            },
        }
