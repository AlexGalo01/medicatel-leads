from __future__ import annotations

from dataclasses import replace

from langsmith import traceable

from mle.observability.langsmith_setup import (
    trace_inputs_initial_state,
    trace_outputs_graph_state,
)
from mle.nodes.exa_webset_node import exa_webset_node
from mle.nodes.planner_node import planner_node
from mle.nodes.relevance_filter_node import relevance_filter_node
from mle.nodes.search_finalize_node import search_finalize_node
from mle.services.job_progress_sink import persist_pipeline_progress
from mle.state.graph_state import LeadSearchGraphState


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
    planner_patch = await planner_node(initial_state)
    state_after_planner = _apply_patch(initial_state, planner_patch)
    await persist_pipeline_progress(initial_state.job_id, state_after_planner)
    if state_after_planner.status == "error":
        return state_after_planner

    exa_patch = await exa_webset_node(state_after_planner)
    state_after_exa = _apply_patch(state_after_planner, exa_patch)
    await persist_pipeline_progress(initial_state.job_id, state_after_exa)
    if state_after_exa.status == "error":
        return state_after_exa

    relevance_patch = await relevance_filter_node(state_after_exa)
    state_after_relevance = _apply_patch(state_after_exa, relevance_patch)
    await persist_pipeline_progress(initial_state.job_id, state_after_relevance)
    if state_after_relevance.status == "error":
        return state_after_relevance

    finalize_patch = await search_finalize_node(state_after_relevance)
    final_state = _apply_patch(state_after_relevance, finalize_patch)
    await persist_pipeline_progress(initial_state.job_id, final_state)
    return final_state
