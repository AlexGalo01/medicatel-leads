from __future__ import annotations

import logging
from dataclasses import replace

from langsmith import traceable

from mle.observability.langsmith_setup import (
    trace_inputs_initial_state,
    trace_outputs_graph_state,
)
from mle.nodes.agentic_search_node import agentic_search_node
from mle.nodes.local_business_search_node import local_business_search_node
from mle.nodes.relevance_filter_node import relevance_filter_node
from mle.nodes.search_finalize_node import search_finalize_node
from mle.services.job_progress_sink import persist_pipeline_progress
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _apply_patch(state: LeadSearchGraphState, patch: dict[str, object]) -> LeadSearchGraphState:
    return replace(
        state,
        status=str(patch.get("status", state.status)),
        current_stage=str(patch.get("current_stage", state.current_stage)),
        progress=int(patch.get("progress", state.progress)),
        search_plan=dict(patch.get("search_plan", state.search_plan)),
        planner_output=dict(patch.get("planner_output", state.planner_output)),
        exa_raw_results=list(patch.get("exa_raw_results", state.exa_raw_results)),
        leads=list(patch.get("leads", state.leads)),
        discarded_leads=list(patch.get("discarded_leads", state.discarded_leads)),
        contact_coverage=float(patch.get("contact_coverage", state.contact_coverage)),
        missing_contact_count=int(patch.get("missing_contact_count", state.missing_contact_count)),
        retry_used=bool(patch.get("retry_used", state.retry_used)),
        errors=list(patch.get("errors", state.errors)),
        langsmith_metadata=dict(patch.get("langsmith_metadata", state.langsmith_metadata)),
    )


MIN_RESULTS_AFTER_FILTER = 40
MAX_SEARCH_ROUNDS = 3


@traceable(
    name="lead_pipeline_graph",
    run_type="chain",
    process_inputs=trace_inputs_initial_state,
    process_outputs=trace_outputs_graph_state,
)
async def run_lead_pipeline(initial_state: LeadSearchGraphState) -> LeadSearchGraphState:
    """
    Pipeline: búsqueda agéntica + filtro de relevancia (con retry) + cierre con vista previa.
    Si los resultados post-filtro son < MIN_RESULTS_AFTER_FILTER, ejecuta rondas adicionales.
    """
    job_id = initial_state.job_id
    try:
        logger.info("Pipeline iniciado: job_id=%s", job_id)

        # Branch: local_business explícito (jobs antiguos) o company con use_places (nuevo flujo unificado)
        exa_category = initial_state.search_plan.get("exa_category")
        use_places = bool(initial_state.search_plan.get("use_places", False))
        if exa_category == "local_business" or (exa_category == "company" and use_places):
            return await _run_local_business_pipeline(initial_state)

        state_current = initial_state

        for round_num in range(1, MAX_SEARCH_ROUNDS + 1):
            logger.info("Ejecutando agentic_search_node ronda %d: job_id=%s", round_num, job_id)
            search_patch = await agentic_search_node(state_current)
            state_after_exa = _apply_patch(state_current, search_patch)
            logger.info(
                "Agentic search ronda %d resultados: job_id=%s, count=%s",
                round_num, job_id, len(state_after_exa.exa_raw_results),
            )
            await persist_pipeline_progress(job_id, state_after_exa)
            if state_after_exa.status == "error":
                logger.error("Agentic search falló: job_id=%s, errors=%s", job_id, state_after_exa.errors)
                return state_after_exa

            logger.info("Ejecutando relevance_filter_node ronda %d: job_id=%s", round_num, job_id)
            relevance_patch = await relevance_filter_node(state_after_exa)
            state_after_relevance = _apply_patch(state_after_exa, relevance_patch)
            kept = len(state_after_relevance.exa_raw_results)
            logger.info(
                "Relevance filtrados ronda %d: job_id=%s, kept=%s",
                round_num, job_id, kept,
            )
            await persist_pipeline_progress(job_id, state_after_relevance)
            if state_after_relevance.status == "error":
                logger.error("Relevance filter falló: job_id=%s, errors=%s", job_id, state_after_relevance.errors)
                return state_after_relevance

            if kept >= MIN_RESULTS_AFTER_FILTER:
                logger.info("Suficientes resultados (%d >= %d) en ronda %d", kept, MIN_RESULTS_AFTER_FILTER, round_num)
                break

            if round_num < MAX_SEARCH_ROUNDS:
                logger.info(
                    "Ronda %d: %d resultados < %d mínimo — ejecutando ronda adicional",
                    round_num, kept, MIN_RESULTS_AFTER_FILTER,
                )
                # Pasar resultados filtrados como base para la siguiente ronda,
                # reseteando exa_calls_used para que Exa esté disponible en la nueva ronda
                fresh_meta = {**state_after_relevance.langsmith_metadata, "exa_calls_used": 0}
                state_current = replace(state_after_relevance, langsmith_metadata=fresh_meta)

        logger.info("Ejecutando search_finalize_node: job_id=%s", job_id)
        finalize_patch = await search_finalize_node(state_after_relevance)
        state_after_finalize = _apply_patch(state_after_relevance, finalize_patch)
        logger.info("Finalize completado: job_id=%s", job_id)
        await persist_pipeline_progress(job_id, state_after_finalize)
        if state_after_finalize.status == "error":
            logger.error("Finalize falló: job_id=%s, errors=%s", job_id, state_after_finalize.errors)
            return state_after_finalize

        logger.info("Pipeline completado exitosamente: job_id=%s", job_id)
        final_state = state_after_finalize
        await persist_pipeline_progress(job_id, final_state)
        return final_state
    except Exception as exc:
        logger.exception("Pipeline exception no capturada: job_id=%s, error=%s", job_id, exc)
        raise


async def _run_local_business_pipeline(initial_state: LeadSearchGraphState) -> LeadSearchGraphState:
    """Pipeline para búsqueda de negocios locales (Google Places + Brave Local).

    Flujo simplificado: local_business_search → search_finalize (sin relevance_filter ni auto_enrich).
    """
    job_id = initial_state.job_id
    try:
        logger.info("Local business pipeline iniciado: job_id=%s", job_id)

        # 1. Búsqueda en Google Places + Brave Local
        search_patch = await local_business_search_node(initial_state)
        state_after_search = _apply_patch(initial_state, search_patch)
        await persist_pipeline_progress(job_id, state_after_search)

        if state_after_search.status == "error":
            logger.error("Local business search falló: job_id=%s, errors=%s", job_id, state_after_search.errors)
            return state_after_search

        logger.info(
            "Local business search resultados: job_id=%s, count=%d",
            job_id, len(state_after_search.exa_raw_results),
        )

        # 2. Finalize — construye preview items (reutiliza el nodo existente)
        finalize_patch = await search_finalize_node(state_after_search)
        state_after_finalize = _apply_patch(state_after_search, finalize_patch)
        await persist_pipeline_progress(job_id, state_after_finalize)

        if state_after_finalize.status == "error":
            logger.error("Finalize falló: job_id=%s, errors=%s", job_id, state_after_finalize.errors)
            return state_after_finalize

        logger.info("Local business pipeline completado: job_id=%s", job_id)
        await persist_pipeline_progress(job_id, state_after_finalize)
        return state_after_finalize

    except Exception as exc:
        logger.exception("Local business pipeline exception: job_id=%s, error=%s", job_id, exc)
        raise
