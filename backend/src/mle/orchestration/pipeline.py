from __future__ import annotations

from dataclasses import replace

from mle.nodes.exa_webset_node import exa_webset_node
from mle.nodes.planner_node import planner_node
from mle.nodes.scoring_cleaning_node import scoring_cleaning_node
from mle.nodes.storage_export_node import storage_export_node
from mle.state.graph_state import LeadSearchGraphState


def _apply_patch(state: LeadSearchGraphState, patch: dict[str, object]) -> LeadSearchGraphState:
    return replace(
        state,
        status=str(patch.get("status", state.status)),
        current_stage=str(patch.get("current_stage", state.current_stage)),
        progress=int(patch.get("progress", state.progress)),
        planner_output=dict(patch.get("planner_output", state.planner_output)),
        webset_id=str(patch.get("webset_id")) if patch.get("webset_id") else state.webset_id,
        webset_status=(
            str(patch.get("webset_status")) if patch.get("webset_status") else state.webset_status
        ),
        webset_poll_attempts=int(
            patch.get("webset_poll_attempts", state.webset_poll_attempts)
        ),
        exa_raw_results=list(patch.get("exa_raw_results", state.exa_raw_results)),
        leads=list(patch.get("leads", state.leads)),
        errors=list(patch.get("errors", state.errors)),
        langsmith_metadata=dict(patch.get("langsmith_metadata", state.langsmith_metadata)),
    )


async def run_lead_pipeline(initial_state: LeadSearchGraphState) -> LeadSearchGraphState:
    planner_patch = await planner_node(initial_state)
    state_after_planner = _apply_patch(initial_state, planner_patch)
    if state_after_planner.status == "error":
        return state_after_planner

    exa_patch = await exa_webset_node(state_after_planner)
    state_after_exa = _apply_patch(state_after_planner, exa_patch)
    if state_after_exa.status == "error":
        return state_after_exa

    scoring_patch = await scoring_cleaning_node(state_after_exa)
    state_after_scoring = _apply_patch(state_after_exa, scoring_patch)
    if state_after_scoring.status == "error":
        return state_after_scoring

    storage_patch = await storage_export_node(state_after_scoring)
    return _apply_patch(state_after_scoring, storage_patch)

