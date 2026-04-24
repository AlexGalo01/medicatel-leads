from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from langsmith import traceable

from mle.clients.exa_client import ExaClient, exa_contents_full_config, finalize_exa_search_payload
from mle.clients.opencli_client import OpenCliClient
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.core.config import effective_exa_search_timeout_seconds, get_settings
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)

MAX_DIRECTORY_EXA_CALLS = 8
MIN_RESULTS_PER_QUERY = 8
MAX_EXA_RESULTS_PER_CALL = 100


def _queries_from_planner(planner_output: dict[str, Any]) -> list[str]:
    search_config = planner_output.get("search_config", {})
    main = str(search_config.get("query", "")).strip()
    extras_raw = search_config.get("additional_queries", [])
    extras: list[str] = []
    if isinstance(extras_raw, list):
        extras = [str(x).strip() for x in extras_raw if str(x).strip()]
    seen_lower: set[str] = set()
    ordered: list[str] = []
    for q in [main] + extras:
        key = q.lower()
        if q and key not in seen_lower:
            seen_lower.add(key)
            ordered.append(q)
    return ordered[:MAX_DIRECTORY_EXA_CALLS]


def _fair_num_results_for_query_slot(total_budget: int, slot: int, num_queries: int) -> int:
    """Reparto entero del presupuesto entre consultas; cada valor entre MIN y 100 (tope API Exa)."""
    if num_queries <= 0:
        return 0
    share = total_budget // num_queries
    rem = total_budget % num_queries
    q = share + (1 if slot < rem else 0)
    return min(MAX_EXA_RESULTS_PER_CALL, max(MIN_RESULTS_PER_QUERY, q))


def _merge_exa_results(batches: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    no_url_idx = 0
    for batch in batches:
        for item in batch:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip().lower()
            if url:
                key = url
            else:
                key = f"nourl:{no_url_idx}"
                no_url_idx += 1
            if key not in merged:
                merged[key] = item
    return list(merged.values())


def _build_search_payload_for_query(
    planner_output: dict[str, Any],
    query: str,
    num_results: int,
) -> dict[str, Any]:
    settings = get_settings()
    search_config = planner_output.get("search_config", {})
    # Si el planner no especifica type, usar el default de settings (deep-reasoning por defecto).
    search_type = str(search_config.get("type") or settings.exa_search_type).strip() or settings.exa_search_type
    include_domains = list(search_config.get("include_domains", []))
    exclude_domains = list(search_config.get("exclude_domains", []))
    exa_category = search_config.get("exa_category")

    payload: dict[str, Any] = {
        "query": query,
        "type": search_type,
        "numResults": num_results,
    }
    rel = planner_output.get("relevance_criteria") if isinstance(planner_output.get("relevance_criteria"), dict) else {}
    iso = str(rel.get("country_iso2") or "").strip().upper()
    if len(iso) == 2 and iso.isalpha():
        payload["userLocation"] = iso
    if exa_category in ("people", "company"):
        payload["category"] = exa_category
    payload["contents"] = exa_contents_full_config(
        text_max_characters=settings.exa_text_max_characters,
        highlights_max_characters=settings.exa_highlights_max_characters,
        subpages=settings.exa_subpages,
    )
    if include_domains:
        payload["includeDomains"] = include_domains
    if exclude_domains:
        payload["excludeDomains"] = exclude_domains
    finalize_exa_search_payload(payload)
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


async def _run_slot_with_prefetch(
    slot_idx: int,
    payload: dict[str, Any],
    num_for_call: int,
    opencli: OpenCliClient | None,
    entity_type: str,
    geo_hint: str,
    exa_client: ExaClient,
    n_queries: int,
    job_id: Any,
    semaphore: asyncio.Semaphore,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Ejecuta un slot Exa y dispara Google Maps para empresas en cuanto llegan los resultados."""
    async with semaphore:
        search_response = await exa_client.search(payload)
    batch_results = _extract_results(search_response)

    # Para búsquedas de empresas: dispara Google Maps inmediatamente en paralelo
    if entity_type == "company" and opencli is not None and opencli.enabled and batch_results:
        items_with_query = [
            (item, f"{item.get('title', '')} {geo_hint}".strip())
            for item in batch_results
            if str(item.get("title") or "").strip()
        ]
        if items_with_query:
            maps_results = await asyncio.gather(
                *[opencli.google_maps(q) for _, q in items_with_query],
                return_exceptions=True,
            )
            for (item, _), mr in zip(items_with_query, maps_results, strict=False):
                if isinstance(mr, dict) and mr:
                    item["_prefetched_maps"] = mr

    logger.info(
        "Exa slot job_id=%s slot=%s/%s pedidos=%s recibidos=%s",
        job_id, slot_idx + 1, n_queries, num_for_call, len(batch_results),
    )
    return batch_results, search_response


@traceable(
    name="exa_webset_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def exa_webset_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Ejecuta una o varias busquedas Exa (fase directorio) y fusiona resultados por URL.
    """
    try:
        planner_output = state.planner_output
        if not planner_output:
            raise ValueError("No existe planner_output para ejecutar Exa Search.")

        search_config = planner_output.get("search_config", {})
        per_query_budget = min(MAX_EXA_RESULTS_PER_CALL, int(search_config.get("num_results", 50)))

        queries = _queries_from_planner(planner_output)
        if not queries:
            raise ValueError("No hay consultas Exa derivadas del planner.")

        n_queries = len(queries)
        per_slot = [per_query_budget for _ in range(n_queries)]

        settings = get_settings()
        exa_client = ExaClient(
            api_key=settings.exa_api_key,
            timeout_seconds=effective_exa_search_timeout_seconds(settings),
        )

        # Determinar entity_type y geo_hint para streaming Google Maps
        exa_category = str(search_config.get("exa_category") or "").strip().lower()
        entity_type = "company" if exa_category == "company" else "person"
        rel = planner_output.get("relevance_criteria") if isinstance(planner_output.get("relevance_criteria"), dict) else {}
        city = str(rel.get("city") or "").strip()
        country = str(rel.get("country_text") or rel.get("country_iso2") or "").strip()
        geo_hint = (f"{city} {country}" if city and country else city or country).strip()

        # Crear OpenCliClient solo para búsquedas de empresas
        opencli: OpenCliClient | None = None
        if entity_type == "company":
            opencli = OpenCliClient(settings)

        # Semáforo para limitar concurrencia en Exa (evitar 429 rate limits)
        exa_semaphore = asyncio.Semaphore(2)

        batches: list[list[dict[str, Any]]] = []
        request_ids: list[str] = []
        last_search_type = str(search_config.get("type", "auto"))
        batch_stats: list[dict[str, int]] = []

        await asyncio.sleep(0)

        # Construir payloads para ejecución paralela
        valid_payloads: list[tuple[int, int, dict[str, Any]]] = []
        for slot_idx, query_text in enumerate(queries):
            num_for_call = per_slot[slot_idx] if slot_idx < len(per_slot) else per_slot[-1]
            payload = _build_search_payload_for_query(planner_output, query_text, num_for_call)
            payload = _ensure_non_empty_query(payload, fallback_query=state.query_text)
            if not str(payload.get("query", "")).strip():
                continue
            valid_payloads.append((slot_idx, num_for_call, payload))

        # Ejecutar todos los slots en paralelo (con semáforo para limitar concurrencia Exa)
        slot_coroutines = [
            _run_slot_with_prefetch(
                slot_idx, payload, num_for_call, opencli, entity_type, geo_hint,
                exa_client, n_queries, state.job_id, exa_semaphore,
            )
            for slot_idx, num_for_call, payload in valid_payloads
        ]
        slot_outcomes = await asyncio.gather(*slot_coroutines, return_exceptions=True)

        # Procesar resultados
        for outcome_idx, (slot_idx, num_for_call, payload) in enumerate(valid_payloads):
            outcome = slot_outcomes[outcome_idx]
            search_type = str(payload.get("type", "auto"))

            if isinstance(outcome, Exception):
                logger.warning(
                    "Exa batch job_id=%s slot=%s/%s falló: %s",
                    state.job_id,
                    slot_idx + 1,
                    n_queries,
                    outcome,
                )
                batches.append([])
                batch_stats.append({"pedidos": num_for_call, "recibidos": 0})
                continue

            batch_results, search_response = outcome
            batches.append(batch_results)
            batch_stats.append({"pedidos": num_for_call, "recibidos": len(batch_results)})
            request_ids.append(str(search_response.get("requestId", "")))
            last_search_type = str(search_response.get("searchType", search_type))

        exa_results = _merge_exa_results(batches)

        # Búsqueda complementaria keyword: cubre directorios y páginas web estáticas
        # que el deep-reasoning semántico no alcanza
        if valid_payloads:
            keyword_payloads = []
            for slot_idx, num_for_call, payload in valid_payloads[:3]:
                kp = {**payload, "type": "keyword", "numResults": 30}
                kp.pop("category", None)
                keyword_payloads.append(kp)

            async def _keyword_search(payload: dict[str, Any]) -> dict[str, Any]:
                async with exa_semaphore:
                    return await exa_client.search(payload)

            keyword_outcomes = await asyncio.gather(
                *[_keyword_search(kp) for kp in keyword_payloads],
                return_exceptions=True,
            )
            keyword_batches: list[list[dict[str, Any]]] = []
            for ko in keyword_outcomes:
                if isinstance(ko, Exception):
                    logger.warning("Exa keyword complementaria falló: %s", ko)
                    keyword_batches.append([])
                else:
                    keyword_batches.append(_extract_results(ko))

            exa_results = _merge_exa_results(batches + keyword_batches)

        logger.info(
            "Exa search node completado job_id=%s unicos_tras_merge=%s llamadas=%s detalle_batches=%s",
            state.job_id,
            len(exa_results),
            len(batches),
            batch_stats,
        )

        return {
            "status": "running",
            "current_stage": "relevance_filter",
            "progress": 68,
            "exa_raw_results": exa_results,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "exa_payload": {
                    "query_count": len(batches),
                    "per_query_numResults": per_slot,
                    "batch_stats": batch_stats,
                },
                "search_type": last_search_type,
                "request_id": ",".join(request_ids)[:500],
                "results_count": len(exa_results),
                "pipeline_phase": "directory",
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
