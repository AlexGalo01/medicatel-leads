"""Nodo de búsqueda de empresa ancla: detecta patrón "empleados de X" y ancla búsqueda a dominio."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from langsmith import traceable

from mle.clients.exa_client import ExaClient
from mle.core.config import effective_exa_search_timeout_seconds, get_settings
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _domain_from_url(url: str) -> str | None:
    """Extrae dominio de una URL (sin www.)."""
    try:
        host = urlparse(url).netloc.lower()
        if not host:
            return None
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return None


@traceable(
    name="company_anchor_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def company_anchor_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Si se detectó búsqueda de empleados de una empresa específica (company_anchor),
    busca el dominio/sitio oficial de la empresa en Exa e inyecta include_domains
    para anclar la búsqueda posterior de empleados.
    """
    try:
        await asyncio.sleep(0)
        planner_out = state.planner_output if isinstance(state.planner_output, dict) else {}
        company_anchor = planner_out.get("company_anchor")

        # Pass-through: sin patrón de empresa, no hacer nada
        if not company_anchor or not isinstance(company_anchor, dict):
            logger.debug("company_anchor_node job_id=%s: sin company_anchor, pass-through", state.job_id)
            return {
                "status": "running",
                "current_stage": "exa_webset",
                "progress": 22,
            }

        company_name = str(company_anchor.get("company_name", "")).strip()
        anchor_query = str(company_anchor.get("anchor_query", company_name)).strip()

        if not company_name or not anchor_query:
            logger.debug("company_anchor_node job_id=%s: fields vacios, pass-through", state.job_id)
            return {
                "status": "running",
                "current_stage": "exa_webset",
                "progress": 22,
            }

        settings = get_settings()
        exa_client = ExaClient(
            api_key=settings.exa_api_key,
            timeout_seconds=effective_exa_search_timeout_seconds(settings),
        )

        # Búsqueda rápida de la empresa (3 resultados, categoría company)
        payload = {
            "query": anchor_query,
            "numResults": 3,
            "category": "company",
            "type": "neural",
        }

        logger.info("company_anchor_node job_id=%s: buscando empresa='%s' con query='%s'",
                    state.job_id, company_name, anchor_query)

        results = await exa_client.search(payload)

        # Extraer dominios de los resultados
        domains: list[str] = []
        for result in results.get("results", []):
            if not isinstance(result, dict):
                continue
            url = str(result.get("url", "")).strip()
            if url:
                domain = _domain_from_url(url)
                if domain and domain not in domains and "linkedin.com" not in domain:
                    domains.append(domain)

        # Siempre incluir LinkedIn (fuente principal de perfiles de empleados)
        if "linkedin.com" not in domains:
            domains.append("linkedin.com")

        # Inyectar en search_config
        search_config = dict(planner_out.get("search_config", {}))
        search_config["include_domains"] = domains
        # exa_category + includeDomains son incompatibles en API Exa; exa_webset_node lo maneja

        updated_planner = {**planner_out, "search_config": search_config}

        logger.info(
            "company_anchor_node job_id=%s completado: empresa='%s' domains=%s",
            state.job_id,
            company_name,
            domains,
        )

        return {
            "status": "running",
            "current_stage": "exa_webset",
            "progress": 22,
            "planner_output": updated_planner,
        }

    except Exception as exc:  # noqa: BLE001
        # Degrade-safe: si falla la búsqueda de empresa, continuar sin ancla
        error_message = f"company_anchor_node degradado: {exc!s}"
        logger.warning("company_anchor_node job_id=%s error: %s", state.job_id, exc)
        return {
            "status": "running",
            "current_stage": "exa_webset",
            "progress": 22,
            # planner_output sin cambios → exa_webset usará la búsqueda sin include_domains
        }
