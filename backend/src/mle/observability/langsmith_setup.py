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
        os.environ.pop("LANGSMITH_TRACING_V2", None)
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    if settings.langsmith_project:
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    endpoint = str(settings.langsmith_endpoint) if settings.langsmith_endpoint else "https://api.smith.langchain.com"
    os.environ["LANGSMITH_ENDPOINT"] = endpoint
    os.environ["LANGCHAIN_ENDPOINT"] = endpoint


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
            if "search_plan" in meta:
                meta["search_plan"] = "<omitido>"
            if "exa_results_preview" in meta and isinstance(meta["exa_results_preview"], list):
                meta["exa_results_preview"] = f"<{len(meta['exa_results_preview'])} items>"
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
        contents = payload.get("contents")
        has_contents = isinstance(contents, dict) and bool(contents)
        return {
            "query_preview": str(payload.get("query", ""))[:400],
            "type": payload.get("type"),
            "numResults": payload.get("numResults"),
            "category": payload.get("category"),
            "includeDomains": payload.get("includeDomains"),
            "has_contents_block": has_contents,
        }
    return {}


def trace_inputs_exa_contents(inputs: dict[str, Any]) -> dict[str, Any]:
    payload = inputs.get("payload")
    if isinstance(payload, dict):
        urls = payload.get("urls")
        url_list = urls if isinstance(urls, list) else []
        n = len(url_list)
        extras = payload.get("extras") if isinstance(payload.get("extras"), dict) else {}
        return {
            "urls_count": n,
            "first_url_preview": str(url_list[0])[:200] if n else "",
            "maxAgeHours": payload.get("maxAgeHours"),
            "has_text": payload.get("text") is not None,
            "has_highlights": payload.get("highlights") is not None,
            "extras_links_requested": extras.get("links"),
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


def trace_outputs_exa_contents_response(output: Any) -> Any:
    """Resumen de /contents: texto y enlaces del primer documento."""
    if not isinstance(output, dict):
        return output
    results = output.get("results", [])
    if not isinstance(results, list) or not results:
        return {
            "results_count": 0,
            "requestId": output.get("requestId"),
            "searchType": output.get("searchType"),
        }
    r0 = results[0]
    links_n = 0
    url_preview = ""
    text_chars = 0
    highlights_n = 0
    if isinstance(r0, dict):
        url_preview = str(r0.get("url", ""))[:160]
        text_chars = len(str(r0.get("text", "")))
        hl = r0.get("highlights")
        if isinstance(hl, list):
            highlights_n = len(hl)
        ex = r0.get("extras")
        if isinstance(ex, dict):
            ln = ex.get("links")
            if isinstance(ln, list):
                links_n = len(ln)
    return {
        "results_count": len(results),
        "requestId": output.get("requestId"),
        "searchType": output.get("searchType"),
        "first_url_preview": url_preview,
        "first_text_chars": text_chars,
        "first_highlights_count": highlights_n,
        "first_extras_links_count": links_n,
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


def trace_inputs_gemini_json_prompt(inputs: dict[str, Any]) -> dict[str, Any]:
    prompt = inputs.get("prompt")
    text = str(prompt) if prompt is not None else ""
    return {
        "prompt_chars": len(text),
        "prompt_preview": text[:500] + ("…" if len(text) > 500 else ""),
    }


def trace_outputs_gemini_json_prompt(output: Any) -> Any:
    if not isinstance(output, dict):
        return output
    entities = output.get("entities")
    n_ent = len(entities) if isinstance(entities, list) else None
    keys = list(output.keys())[:20]
    return {
        "top_level_keys": keys,
        "entities_count": n_ent,
        "response_size_keys": len(output),
    }


def trace_inputs_gemini_expand_plan(inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_query_preview": str(inputs.get("user_query", ""))[:240],
        "search_focus": inputs.get("search_focus"),
        "contact_channels_count": len(inputs.get("contact_channels") or []),
        "has_notes": bool(str(inputs.get("notes") or "").strip()),
    }


def trace_inputs_gemini_expand_query(inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_query_preview": str(inputs.get("user_query", ""))[:240],
        "search_focus": inputs.get("search_focus"),
        "contact_channels_count": len(inputs.get("contact_channels") or []),
        "has_notes": bool(str(inputs.get("notes") or "").strip()),
    }


def trace_outputs_gemini_search_plan(output: Any) -> Any:
    if not isinstance(output, dict):
        return output
    add_q = output.get("additional_queries")
    n_add = len(add_q) if isinstance(add_q, list) else 0
    return {
        "main_query_preview": str(output.get("main_query", ""))[:200],
        "additional_queries_count": n_add,
        "exa_category": output.get("exa_category"),
        "has_clarifying_question": bool(output.get("clarifying_question")),
    }


def trace_outputs_gemini_expand_query(output: Any) -> Any:
    if not isinstance(output, dict):
        return output
    return {
        "expanded_query_preview": str(output.get("expanded_query", ""))[:220],
        "has_negative_constraints": bool(str(output.get("negative_constraints") or "").strip()),
    }
