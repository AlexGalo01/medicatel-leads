from __future__ import annotations

import logging
from dataclasses import replace

from langsmith import traceable

from mle.observability.langsmith_setup import (
    trace_inputs_initial_state,
    trace_outputs_graph_state,
)
from mle.nodes.company_anchor_node import company_anchor_node
from mle.nodes.exa_webset_node import exa_webset_node
from mle.nodes.planner_node import planner_node
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


@traceable(
    name="lead_pipeline_graph",
    run_type="chain",
    process_inputs=trace_inputs_initial_state,
    process_outputs=trace_outputs_graph_state,
)
async def run_lead_pipeline(initial_state: LeadSearchGraphState) -> LeadSearchGraphState:
    """
    Pipeline demo: planner + Exa + filtro de relevancia + cierre con vista previa.
    Ver AGENT_TO_DO.md para reactivar limpieza, reintento y persistencia de leads.
    """
    job_id = initial_state.job_id
    try:
        logger.info("Pipeline iniciado: job_id=%s", job_id)

        logger.info("Ejecutando planner_node: job_id=%s", job_id)
        planner_patch = await planner_node(initial_state)
        state_after_planner = _apply_patch(initial_state, planner_patch)
        await persist_pipeline_progress(job_id, state_after_planner)
        if state_after_planner.status == "error":
            logger.error("Planner falló: job_id=%s, errors=%s", job_id, state_after_planner.errors)
            return state_after_planner

        logger.info("Ejecutando company_anchor_node: job_id=%s", job_id)
        anchor_patch = await company_anchor_node(state_after_planner)
        state_after_anchor = _apply_patch(state_after_planner, anchor_patch)
        await persist_pipeline_progress(job_id, state_after_anchor)
        if state_after_anchor.status == "error":
            logger.error("Anchor falló: job_id=%s, errors=%s", job_id, state_after_anchor.errors)
            return state_after_anchor

        logger.info("Ejecutando exa_webset_node: job_id=%s", job_id)
        exa_patch = await exa_webset_node(state_after_anchor)
        state_after_exa = _apply_patch(state_after_anchor, exa_patch)
        logger.info("Exa resultados: job_id=%s, count=%s", job_id, len(state_after_exa.exa_raw_results))
        await persist_pipeline_progress(job_id, state_after_exa)
        if state_after_exa.status == "error":
            logger.error("Exa falló: job_id=%s, errors=%s", job_id, state_after_exa.errors)
            return state_after_exa

        logger.info("Ejecutando relevance_filter_node: job_id=%s", job_id)
        relevance_patch = await relevance_filter_node(state_after_exa)
        state_after_relevance = _apply_patch(state_after_exa, relevance_patch)
        logger.info("Relevance filtrados: job_id=%s, count=%s", job_id, len(state_after_relevance.leads))
        await persist_pipeline_progress(job_id, state_after_relevance)
        if state_after_relevance.status == "error":
            logger.error("Relevance filter falló: job_id=%s, errors=%s", job_id, state_after_relevance.errors)
            return state_after_relevance

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
