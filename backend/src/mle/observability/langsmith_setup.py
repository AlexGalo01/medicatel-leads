from __future__ import annotations

import os
from typing import Any
from uuid import UUID

from mle.core.config import get_settings
from mle.state.graph_state import LeadSearchGraphState

_configured = False


def configure_langsmith_env() -> None:
    """
    Sincroniza Settings (pydantic) con variables de entorno que consume el SDK de LangSmith.

    Idempotente; conviene llamarla al arranque de la API y al inicio del pipeline por si el job
    se ejecuta fuera del proceso de uvicorn.
    """
    global _configured
    if _configured:
        return
    _configured = True

    settings = get_settings()
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    if settings.langsmith_project:
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    if settings.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = str(settings.langsmith_endpoint)


def summarize_graph_state(state: LeadSearchGraphState) -> dict[str, Any]:
    qt = state.query_text or ""
    return {
        "job_id": str(state.job_id),
        "query_text_preview": qt[:500] + ("…" if len(qt) > 500 else ""),
        "status": state.status,
        "current_stage": state.current_stage,
        "progress": state.progress,
        "exa_raw_count": len(state.exa_raw_results),
        "leads_count": len(state.leads),
        "discarded_count": len(state.discarded_leads),
        "contact_coverage": state.contact_coverage,
        "missing_contact_count": state.missing_contact_count,
        "retry_used": state.retry_used,
        "errors_count": len(state.errors),
    }


def compact_node_patch(patch: Any) -> Any:
    """Evita enviar listas enormes o snapshots completos a LangSmith."""
    if not isinstance(patch, dict):
        return patch
    result: dict[str, Any] = {}
    for key, value in patch.items():
        if key == "exa_raw_results" and isinstance(value, list):
            result[key] = f"<{len(value)} resultados>"
        elif key in ("leads", "discarded_leads") and isinstance(value, list):
            result[key] = f"<{len(value)} items>"
        elif key == "langsmith_metadata" and isinstance(value, dict):
            meta = dict(value)
            for huge in ("exa_state_snapshot", "planner_state_snapshot", "scoring_state_snapshot"):
                if huge in meta:
                    meta[huge] = "<omitido>"
            if "exa_payload" in meta:
                meta["exa_payload"] = "<omitido>"
            result[key] = meta
        else:
            result[key] = value
    return result


def trace_inputs_from_graph_state(inputs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in inputs.items():
        if key == "self":
            continue
        if isinstance(value, LeadSearchGraphState):
            out[key] = summarize_graph_state(value)
        else:
            out[key] = value
    return out


def trace_inputs_job_id(inputs: dict[str, Any]) -> dict[str, Any]:
    raw = inputs.get("job_id")
    return {"job_id": str(raw) if isinstance(raw, UUID) else raw}


def trace_inputs_initial_state(inputs: dict[str, Any]) -> dict[str, Any]:
    state = inputs.get("initial_state")
    if isinstance(state, LeadSearchGraphState):
        return {"initial_state": summarize_graph_state(state)}
    return trace_inputs_from_graph_state(inputs)


def trace_outputs_graph_state(output: Any) -> Any:
    if isinstance(output, LeadSearchGraphState):
        return summarize_graph_state(output)
    return output


def trace_inputs_exa_search(inputs: dict[str, Any]) -> dict[str, Any]:
    payload = inputs.get("payload")
    if isinstance(payload, dict):
        return {
            "query_preview": str(payload.get("query", ""))[:400],
            "type": payload.get("type"),
            "numResults": payload.get("numResults"),
        }
    return {}


def trace_outputs_exa_response(output: Any) -> Any:
    if not isinstance(output, dict):
        return output
    results = output.get("results", [])
    n = len(results) if isinstance(results, list) else 0
    return {
        "results_count": n,
        "requestId": output.get("requestId"),
        "searchType": output.get("searchType"),
    }


def trace_inputs_gemini_score(inputs: dict[str, Any]) -> dict[str, Any]:
    payload = inputs.get("lead_payload")
    if isinstance(payload, dict):
        return {
            "full_name_preview": str(payload.get("full_name", ""))[:120],
            "has_email": bool(payload.get("email")),
            "has_whatsapp": bool(payload.get("whatsapp")),
            "has_linkedin": bool(payload.get("linkedin_url")),
        }
    return {}


def trace_outputs_gemini_score(output: Any) -> Any:
    if not isinstance(output, dict):
        return output
    reasoning = str(output.get("reasoning", ""))
    return {
        "score": output.get("score"),
        "reasoning_preview": reasoning[:240] + ("…" if len(reasoning) > 240 else ""),
    }
