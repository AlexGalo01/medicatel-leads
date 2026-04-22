from __future__ import annotations

import asyncio
import logging
from typing import Any

from langsmith import traceable

from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.services.exa_preview_enrich_service import enrich_exa_preview_rows
from mle.services.relevance_filter_service import filter_exa_list_heuristic_only
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)

PIPELINE_MODE_SEARCH_ONLY = "presearch_and_search_only"
MAX_EXA_PREVIEW_ITEMS = 60
MAX_EXA_ACCUMULATED_RAW = 120
HIGHLIGHT_JOIN_MAX = 1800


def _url_key_for_merge(url: str) -> str:
    return str(url or "").strip().lower().rstrip("/")


def _preview_item(raw: dict[str, Any], index: int) -> dict[str, Any]:
    title = str(raw.get("title", "")).strip()[:300]
    url = str(raw.get("url", "")).strip()[:2000]
    highlights = raw.get("highlights")
    snippet = ""
    if isinstance(highlights, list):
        snippet = " | ".join(str(h) for h in highlights[:8])[:HIGHLIGHT_JOIN_MAX]
    elif raw.get("text"):
        snippet = str(raw.get("text", ""))[:HIGHLIGHT_JOIN_MAX]
    return {
        "index": index + 1,
        "title": title or url or "Sin titulo",
        "url": url,
        "snippet": snippet or None,
    }


def _build_exa_preview(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(results[:MAX_EXA_PREVIEW_ITEMS]):
        if isinstance(item, dict):
            out.append(_preview_item(item, i))
    return out


@traceable(
    name="search_finalize_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def search_finalize_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Cierra el pipeline en modo demo: solo prebusqueda + Exa.
    Serializa una vista previa acotada de resultados para la API y el frontend.
    """
    await asyncio.sleep(0)
    accumulated = [dict(item) for item in state.exa_raw_results[:MAX_EXA_ACCUMULATED_RAW] if isinstance(item, dict)]
    preview = _build_exa_preview(accumulated)
    try:
        preview = await enrich_exa_preview_rows(preview)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Enriquecimiento preview Exa omitido job_id=%s: %s", state.job_id, exc)

    finalize_heuristic_meta: dict[str, Any] = {}
    planner_out = state.planner_output if isinstance(state.planner_output, dict) else {}
    rel = planner_out.get("relevance_criteria") if isinstance(planner_out.get("relevance_criteria"), dict) else {}
    iso = str(rel.get("country_iso2") or "").strip().upper()
    if len(iso) == 2 and accumulated and preview:
        enriched_by_url: dict[str, dict[str, Any]] = {}
        for row in preview:
            if isinstance(row, dict):
                uk = _url_key_for_merge(str(row.get("url", "")))
                if uk:
                    enriched_by_url[uk] = row
        composite: list[dict[str, Any]] = []
        for raw_row in accumulated:
            if not isinstance(raw_row, dict):
                continue
            merged_row = dict(raw_row)
            uk = _url_key_for_merge(str(merged_row.get("url", "")))
            if uk and uk in enriched_by_url:
                sn = enriched_by_url[uk].get("snippet")
                if isinstance(sn, str) and sn.strip():
                    merged_row["snippet"] = sn.strip()
            composite.append(merged_row)
        filtered_composite, finalize_heuristic_meta = filter_exa_list_heuristic_only(composite, iso)
        order_urls = [_url_key_for_merge(str(x.get("url", ""))) for x in filtered_composite if str(x.get("url", "")).strip()]
        by_url = {
            _url_key_for_merge(str(x.get("url", ""))): x
            for x in accumulated
            if isinstance(x, dict) and str(x.get("url", "")).strip()
        }
        accumulated = []
        for uk in order_urls:
            if uk in by_url:
                accumulated.append(by_url[uk])
        accumulated = accumulated[:MAX_EXA_ACCUMULATED_RAW]
        preview_out: list[dict[str, Any]] = []
        for i, raw_row in enumerate(accumulated):
            base = _preview_item(raw_row, i)
            uk = _url_key_for_merge(str(raw_row.get("url", "")))
            if uk and uk in enriched_by_url:
                old = enriched_by_url[uk]
                base["specialty"] = str(old.get("specialty") or "")
                base["city"] = str(old.get("city") or "")
            preview_out.append(base)
        preview = preview_out

    logger.info(
        "search_finalize job_id=%s resultados_exa=%s acumulados_guardados=%s preview=%s heuristic_meta=%s",
        state.job_id,
        len(state.exa_raw_results),
        len(accumulated),
        len(preview),
        finalize_heuristic_meta,
    )
    meta_out = {
        **state.langsmith_metadata,
        "pipeline_mode": PIPELINE_MODE_SEARCH_ONLY,
        "exa_results_preview": preview,
        "exa_accumulated_raw": accumulated,
        "exa_more_rounds": 0,
    }
    if finalize_heuristic_meta:
        meta_out = {**meta_out, **finalize_heuristic_meta}
    return {
        "status": "completed",
        "current_stage": "done",
        "progress": 100,
        "langsmith_metadata": meta_out,
    }
