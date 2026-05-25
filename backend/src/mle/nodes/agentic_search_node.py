"""Nodo agéntico de búsqueda: el LLM decide queries iterativamente usando Exa y Brave como tools."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any

from langsmith import traceable

from mle.clients.brave_client import BraveSearchClient
from mle.clients.exa_client import ExaClient, exa_contents_highlights_config, finalize_exa_search_payload
from mle.clients.openai_client import OpenAIClient
from mle.core.config import effective_exa_search_timeout_seconds, get_settings
from mle.nodes.planner_node import _build_planner_output
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.services.job_progress_sink import append_activity_entry
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8
MAX_ACCUMULATED_RESULTS = 400
MAX_EXA_CALLS_PER_PIPELINE = 8

# Restricción geográfica fija — mientras el producto opera exclusivamente en Honduras
FORCED_COUNTRY_ISO2 = "HN"
FORCED_COUNTRY_NAME = "Honduras"

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Busca perfiles profesionales, empresas o directorios en la web. "
                "Usa queries descriptivas en español. Cada llamada ejecuta la búsqueda y retorna títulos + URLs. "
                "Puedes llamar esta herramienta múltiples veces con queries diferentes para ampliar cobertura."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query de búsqueda en español. Sé específico: incluye profesión, ciudad, país.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["people", "company", "general"],
                        "description": "Tipo de resultados: 'people' para perfiles individuales, 'company' para empresas, 'general' sin restricción.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Cantidad de resultados deseados (10-60).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_search",
            "description": (
                "Finaliza la búsqueda cuando consideras que tienes suficientes resultados relevantes, "
                "o cuando ya agotaste las variaciones de query útiles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "Breve explicación de por qué finalizas.",
                    },
                },
                "required": ["reasoning"],
            },
        },
    },
]


def _build_system_prompt(state: LeadSearchGraphState, planner_output: dict[str, Any], *, prior_count: int = 0) -> str:
    """Construye el system prompt con el contexto de búsqueda."""
    search_config = planner_output.get("search_config", {})
    relevance = planner_output.get("relevance_criteria", {})
    company_anchor = planner_output.get("company_anchor")

    entity_hint = relevance.get("role_or_stack_hint", "") or ""
    exa_category = search_config.get("exa_category") or "general"

    anchor_block = ""
    if company_anchor and isinstance(company_anchor, dict):
        company_name = company_anchor.get("company_name", "")
        if company_name:
            anchor_block = (
                f"\nPATRÓN ESPECIAL: El usuario busca empleados/personal de '{company_name}'. "
                f"Incluye queries específicas para encontrar perfiles de esa empresa (LinkedIn, sitio web)."
            )

    prior_block = ""
    if prior_count > 0:
        prior_block = (
            f"\nRONDA ADICIONAL: Ya tienes {prior_count} resultados de rondas previas, pero no son suficientes. "
            "Necesitas encontrar MÁS resultados con queries DIFERENTES a las anteriores. "
            "Prueba sinónimos, directorios locales, variaciones de ciudad, o sitios específicos del sector.\n"
        )

    return (
        "Eres un agente de búsqueda web especializado en encontrar perfiles profesionales y empresas.\n"
        "Tienes acceso a la herramienta `web_search` que busca en múltiples motores (Exa + Brave).\n\n"
        "CONTEXTO DE BÚSQUEDA:\n"
        f"- Consulta del usuario: {state.query_text}\n"
        f"- Ubicación FIJA: Honduras (TODAS las búsquedas son exclusivamente en Honduras)\n"
        f"- Tipo de entidad: {entity_hint or exa_category}\n"
        f"- Categoría Exa: {exa_category}\n"
        f"{anchor_block}{prior_block}\n\n"
        "RESTRICCIÓN CRÍTICA — PAÍS:\n"
        "⚠️  TODAS las queries DEBEN incluir 'Honduras'. Sin excepción.\n"
        "   Ejemplos correctos: 'ginecólogos Honduras', 'clínicas dentales Tegucigalpa Honduras', 'abogados San Pedro Sula Honduras'\n"
        "   NUNCA envíes una query sin 'Honduras' al final.\n\n"
        "INSTRUCCIONES:\n"
        "1. Usa `web_search` MÚLTIPLES veces con queries variadas. Pide 100 resultados por consulta.\n"
        "2. Varía las queries: por ciudad (Tegucigalpa, San Pedro Sula, La Ceiba, Choluteca...), por sinónimos de la especialidad, por tipo de sitio (directorios, clínicas, LinkedIn).\n"
        "3. NUNCA uses palabras como 'email', 'whatsapp', 'contacto' en las queries — contaminan resultados.\n"
        "4. Usa category='people' para profesionales individuales, 'company' para empresas/clínicas, 'general' si los otros dan pocos resultados.\n"
        "5. Prueba variaciones: 'médicos [especialidad] Honduras', '[especialidad] Tegucigalpa', 'directorio [especialidad] Honduras', 'clínica [especialidad] San Pedro Sula'.\n"
        "6. EVITA AGREGADORES: Si ves listas ('Top 10...'), refina hacia perfiles individuales.\n"
        "7. Finaliza con `finalize_search` solo cuando tengas 80+ resultados O hayas agotado variaciones útiles.\n"
        "8. Si una query devuelve pocos resultados, intenta con otra ciudad o sinónimo ANTES de finalizar.\n"
    )


def _summarize_results_for_llm(results: list[dict[str, Any]], max_items: int = 30) -> str:
    """Resume los resultados para que el LLM evalúe si necesita buscar más."""
    if not results:
        return "Sin resultados."

    lines = [f"Total resultados acumulados: {len(results)}\n"]
    for i, item in enumerate(results[:max_items]):
        title = str(item.get("title", "")).strip()[:80]
        url = str(item.get("url", "")).strip()[:100]
        source = item.get("source_type", "exa")
        lines.append(f"[{i + 1}] ({source}) {title} | {url}")

    if len(results) > max_items:
        lines.append(f"... y {len(results) - max_items} más")
    return "\n".join(lines)


async def _execute_web_search(
    args: dict[str, Any],
    *,
    settings: Any,
    planner_output: dict[str, Any],
    seen_urls: set[str],
    job_id: Any,
    use_exa: bool = True,
    facebook_parallel: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """Ejecuta búsqueda web. Si use_exa=True incluye Exa + Brave, sino solo Brave."""
    query = str(args.get("query", "")).strip()
    category = str(args.get("category", "general")).strip()
    num_results = min(100, max(10, int(args.get("num_results", 50))))

    if not query:
        return [], "Error: query vacía."

    # Forzar Honduras en la query si no está presente
    if FORCED_COUNTRY_NAME.lower() not in query.lower():
        query = f"{query} {FORCED_COUNTRY_NAME}"

    if category not in ("people", "company"):
        category = None  # type: ignore[assignment]

    search_config = planner_output.get("search_config", {})
    # Forzar siempre Honduras independientemente de lo que detectó el planner
    iso = FORCED_COUNTRY_ISO2

    # Exa (solo si use_exa=True)
    exa_coro = None
    if use_exa:
        search_type = str(search_config.get("type") or settings.exa_search_type)
        if category in ("people", "company") and search_type in ("deep-reasoning",):
            search_type = "neural"

        exa_payload: dict[str, Any] = {
            "query": query,
            "type": search_type,
            "numResults": num_results,
        }
        if len(iso) == 2 and iso.isalpha():
            exa_payload["userLocation"] = iso
        if category:
            exa_payload["category"] = category
        exa_payload["contents"] = exa_contents_highlights_config(
            max_characters=settings.exa_highlights_max_characters,
        )
        include_domains = list(search_config.get("include_domains", []))
        if include_domains:
            exa_payload["includeDomains"] = include_domains
        finalize_exa_search_payload(exa_payload)

        exa_client = ExaClient(
            api_key=settings.exa_api_key,
            timeout_seconds=effective_exa_search_timeout_seconds(settings),
        )
        exa_coro = exa_client.search(exa_payload)

    # Brave (siempre)
    brave_coros: list[Any] = []
    if settings.brave_search_enabled and settings.brave_search_api_key:
        brave_client = BraveSearchClient(
            api_key=settings.brave_search_api_key,
            timeout_seconds=settings.brave_search_timeout_seconds,
        )
        brave_country = iso if len(iso) == 2 else None
        # Append site: restriction for Brave if include_domains is set
        brave_query = query
        include_domains = list(search_config.get("include_domains", []))
        if include_domains:
            brave_query = f"site:{include_domains[0]} {query}"
        brave_coros.append(brave_client.web_search(brave_query, country=brave_country, count=20, pages=2))

        # Facebook parallel: add an extra Brave search restricted to facebook.com
        if facebook_parallel and not include_domains:
            fb_query = f"site:facebook.com {query}"
            brave_coros.append(brave_client.web_search(fb_query, country=brave_country, count=20, pages=2))

    # Ejecutar en paralelo
    coros_to_run = ([exa_coro] if exa_coro else []) + brave_coros
    all_outcomes = await asyncio.gather(*coros_to_run, return_exceptions=True)

    exa_outcome = all_outcomes[0] if exa_coro else None
    brave_outcomes = all_outcomes[1:] if exa_coro else all_outcomes

    batch: list[dict[str, Any]] = []
    exa_failed = False

    if exa_outcome is None:
        pass  # Exa no se usó
    elif isinstance(exa_outcome, Exception):
        logger.warning("Agentic search Exa falló job_id=%s: %s", job_id, exa_outcome)
        exa_failed = True
    else:
        for r in exa_outcome.get("results", []):
            if isinstance(r, dict):
                batch.append(r)

    for brave_outcome in brave_outcomes:
        if isinstance(brave_outcome, Exception):
            logger.warning("Agentic search Brave falló job_id=%s: %s", job_id, brave_outcome)
        elif isinstance(brave_outcome, list):
            batch.extend(brave_outcome)

    # Dedup contra ya vistos
    new_items: list[dict[str, Any]] = []
    for item in batch:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip().lower().rstrip("/")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        new_items.append(dict(item))

    source_info = []
    if exa_outcome is None:
        source_info.append("Exa: omitido")
    elif exa_failed:
        source_info.append("Exa: no disponible")
    else:
        source_info.append(f"Exa: {len([r for r in batch if r.get('source_type') != 'brave_web'])} resultados")
    brave_count = len([r for r in batch if r.get("source_type") == "brave_web"])
    if brave_count:
        source_info.append(f"Brave: {brave_count} resultados")

    summary = (
        f"Query: '{query}' | {' | '.join(source_info)} | "
        f"Nuevos (no duplicados): {len(new_items)}"
    )
    logger.info("Agentic web_search job_id=%s: %s", job_id, summary)

    # Log activity entry para el frontend
    exa_count = len([r for r in batch if r.get("source_type") != "brave_web"])
    brave_count = len([r for r in batch if r.get("source_type") == "brave_web"])
    asyncio.create_task(append_activity_entry(job_id, {
        "t": datetime.utcnow().isoformat(timespec="seconds"),
        "msg": f"Buscando: {query}",
        "found": len(new_items),
        "exa": exa_count,
        "brave": brave_count,
    }))

    return new_items, summary


@traceable(
    name="agentic_search_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def agentic_search_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Nodo agéntico que reemplaza planner + company_anchor + exa_webset.
    El LLM decide las queries iterativamente usando tool calling.
    """
    try:
        settings = get_settings()

        # 1. Ejecutar planner para obtener contexto estructurado
        planner_output = _build_planner_output(state).model_dump()

        # Inject include_domains from search_plan (e.g., facebook focus)
        brave_only = bool(state.search_plan.get("brave_only"))
        plan_domains = state.search_plan.get("include_domains")
        if plan_domains and isinstance(plan_domains, list):
            sc = dict(planner_output.get("search_config", {}))
            sc["include_domains"] = plan_domains
            planner_output["search_config"] = sc
            logger.info("Injected include_domains=%s from search_plan job_id=%s", plan_domains, state.job_id)
        if brave_only:
            logger.info("brave_only mode — Exa disabled for job_id=%s", state.job_id)

        # 2. Ejecutar company_anchor si aplica (reutilizar lógica inline)
        company_anchor = planner_output.get("company_anchor")
        if company_anchor and isinstance(company_anchor, dict):
            company_name = str(company_anchor.get("company_name", "")).strip()
            anchor_query = str(company_anchor.get("anchor_query", company_name)).strip()
            if company_name and anchor_query:
                try:
                    from urllib.parse import urlparse
                    exa_client = ExaClient(
                        api_key=settings.exa_api_key,
                        timeout_seconds=effective_exa_search_timeout_seconds(settings),
                    )
                    anchor_results = await exa_client.search({
                        "query": anchor_query, "numResults": 3,
                        "category": "company", "type": "neural",
                    })
                    domains: list[str] = []
                    for r in anchor_results.get("results", []):
                        url = str(r.get("url", "")).strip()
                        if url:
                            host = urlparse(url).netloc.lower()
                            if host.startswith("www."):
                                host = host[4:]
                            if host and host not in domains and "linkedin.com" not in host:
                                domains.append(host)
                    if "linkedin.com" not in domains:
                        domains.append("linkedin.com")
                    sc = dict(planner_output.get("search_config", {}))
                    sc["include_domains"] = domains
                    planner_output["search_config"] = sc
                    logger.info("Agentic company_anchor job_id=%s: domains=%s", state.job_id, domains)
                except Exception as exc:
                    logger.warning("Agentic company_anchor degradado job_id=%s: %s", state.job_id, exc)

        # 3. Verificar que tenemos OpenAI disponible
        if not settings.openai_api_key:
            logger.warning("OpenAI no disponible para agentic search, cayendo a pipeline estático")
            return await _fallback_static_search(state, planner_output)

        openai_client = OpenAIClient(
            api_key=settings.openai_api_key,
            model_name=settings.openai_model,
            timeout_seconds=60.0,
        )

        # 4. Loop agéntico — inicializar con resultados de rondas previas (si las hay)
        all_results: list[dict[str, Any]] = [
            dict(r) for r in state.exa_raw_results if isinstance(r, dict)
        ]
        seen_urls: set[str] = {
            str(r.get("url", "")).strip().lower().rstrip("/")
            for r in all_results if r.get("url")
        }
        warnings: list[str] = []
        exa_calls_used = int(state.langsmith_metadata.get("exa_calls_used", 0))
        system_prompt = _build_system_prompt(state, planner_output, prior_count=len(all_results))

        async def tool_executor(fn_name: str, fn_args: dict[str, Any]) -> str:
            nonlocal exa_calls_used
            if fn_name == "web_search":
                # brave_only desactiva Exa (e.g. Facebook focus)
                should_use_exa = (not brave_only) and exa_calls_used < MAX_EXA_CALLS_PER_PIPELINE
                new_items, summary = await _execute_web_search(
                    fn_args,
                    settings=settings,
                    planner_output=planner_output,
                    seen_urls=seen_urls,
                    job_id=state.job_id,
                    use_exa=should_use_exa,
                    facebook_parallel=bool(state.search_plan.get("facebook_parallel")),
                )
                if should_use_exa:
                    exa_calls_used += 1
                all_results.extend(new_items)
                result_preview = _summarize_results_for_llm(all_results)
                return f"{summary}\n\n{result_preview}"

            elif fn_name == "finalize_search":
                reasoning = fn_args.get("reasoning", "")
                logger.info("Agentic finalize_search job_id=%s: %s", state.job_id, reasoning)
                return json.dumps({"status": "finalized", "total_results": len(all_results)})

            return json.dumps({"error": f"Tool desconocido: {fn_name}"})

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Busca: {state.query_text}"},
        ]

        tool_call_count = 0
        try:
            final_messages = await openai_client.chat_with_tools(
                messages=messages,
                tools=_TOOLS,
                max_iterations=MAX_ITERATIONS,
                tool_executor=tool_executor,
            )
            tool_call_count = sum(1 for m in final_messages if isinstance(m, dict) and m.get("role") == "tool")
            logger.info(
                "Agentic search completado job_id=%s: %d resultados, %d tool calls",
                state.job_id, len(all_results), tool_call_count,
            )
        except Exception as exc:
            logger.warning("Agentic tool loop falló job_id=%s: %s — usando resultados parciales", state.job_id, exc)
            warnings.append(f"El agente de búsqueda encontró un error: {exc!s}. Resultados parciales.")

        # Limitar resultados
        exa_results = all_results[:MAX_ACCUMULATED_RESULTS]

        return {
            "status": "running",
            "current_stage": "relevance_filter",
            "progress": 68,
            "planner_output": planner_output,
            "exa_raw_results": exa_results,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "warnings": warnings,
                "exa_calls_used": exa_calls_used,
                "agentic_search": {
                    "tool_calls": tool_call_count,
                    "results_count": len(exa_results),
                    "exa_calls_used": exa_calls_used,
                },
                "results_count": len(exa_results),
                "pipeline_phase": "directory",
            },
        }
    except Exception as exc:  # noqa: BLE001
        error_message = f"Agentic search node fallo: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "error",
            "current_stage": "agentic_search",
            "progress": state.progress,
            "exa_raw_results": [],
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "agentic_error": error_message,
                "agentic_state_snapshot": asdict(state),
            },
        }


async def _fallback_static_search(
    state: LeadSearchGraphState,
    planner_output: dict[str, Any],
) -> dict[str, object]:
    """Fallback al flujo estático si OpenAI no está disponible."""
    from mle.nodes.exa_webset_node import exa_webset_node

    # Inyectar planner_output en el state para que exa_webset_node lo use
    from dataclasses import replace
    patched_state = replace(
        state,
        planner_output=planner_output,
        status="running",
        current_stage="exa_webset",
        progress=20,
    )
    return await exa_webset_node(patched_state)
