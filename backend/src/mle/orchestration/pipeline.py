from __future__ import annotations

from dataclasses import replace

from langsmith import traceable

from mle.observability.langsmith_setup import (
    trace_inputs_initial_state,
    trace_outputs_graph_state,
)
from mle.nodes.exa_webset_node import exa_webset_node
from mle.nodes.contact_retry_node import contact_retry_node
from mle.nodes.lead_purification_node import lead_purification_node
from mle.nodes.planner_node import planner_node
from mle.nodes.scoring_cleaning_node import scoring_cleaning_node
from mle.nodes.storage_export_node import storage_export_node
from mle.services.job_progress_sink import persist_pipeline_progress
from mle.state.graph_state import LeadSearchGraphState


def _apply_patch(state: LeadSearchGraphState, patch: dict[str, object]) -> LeadSearchGraphState:
    return replace(
        state,
        status=str(patch.get("status", state.status)),
        current_stage=str(patch.get("current_stage", state.current_stage)),
        progress=int(patch.get("progress", state.progress)),
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

    scoring_patch = await scoring_cleaning_node(state_after_exa)
    state_after_scoring = _apply_patch(state_after_exa, scoring_patch)
    await persist_pipeline_progress(initial_state.job_id, state_after_scoring)
    if state_after_scoring.status == "error":
        return state_after_scoring

    purification_patch = await lead_purification_node(state_after_scoring)
    state_after_purification = _apply_patch(state_after_scoring, purification_patch)
    await persist_pipeline_progress(initial_state.job_id, state_after_purification)
    if state_after_purification.status == "error":
        return state_after_purification

    retry_patch = await contact_retry_node(state_after_purification)
    state_after_retry = _apply_patch(state_after_purification, retry_patch)
    await persist_pipeline_progress(initial_state.job_id, state_after_retry)
    if state_after_retry.status == "error":
        return state_after_retry

    storage_patch = await storage_export_node(state_after_retry)
    final_state = _apply_patch(state_after_retry, storage_patch)
    await persist_pipeline_progress(initial_state.job_id, final_state)
    return final_state

