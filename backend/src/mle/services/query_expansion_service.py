from __future__ import annotations

import logging
from typing import Any

from langsmith import traceable

from mle.core.config import get_settings
from mle.clients.llm_factory import get_llm_client
from mle.schemas.search_plan import SearchPlan, search_plan_from_fallback

logger = logging.getLogger(__name__)


def _coerce_raw_plan(raw: dict[str, Any], contact_channels: list[str]) -> dict[str, Any]:
    geo_in = raw.get("geo")
    if isinstance(geo_in, dict):
        geo_obj = {"country": str(geo_in.get("country", "")).strip(), "city": str(geo_in.get("city", "")).strip()}
    else:
        geo_obj = {"country": "", "city": ""}

    add_q = raw.get("additional_queries") or []
    if not isinstance(add_q, list):
        add_q = []

    req = raw.get("required_channels") or contact_channels
    if not isinstance(req, list):
        req = list(contact_channels)

    cq = raw.get("clarifying_question")
    if cq is not None and str(cq).strip() == "":
        cq = None

    return {
        "entity_type": str(raw.get("entity_type", "")).strip(),
        "geo": geo_obj,
        "main_query": str(raw.get("main_query", "")).strip(),
        "additional_queries": add_q,
        "required_channels": [str(x).strip() for x in req if str(x).strip()],
        "negative_constraints": str(raw.get("negative_constraints", "")).strip(),
        "clarifying_question": cq,
        "exa_category": raw.get("exa_category"),
    }


@traceable(
    name="expand_user_search_query",
    run_type="chain",
    metadata={"phase": "directory"},
    tags=["search-job", "query-expansion"],
)
async def expand_user_search_query(
    user_query: str,
    contact_channels: list[str],
    search_focus: str | None,
    notes: str | None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """
    Devuelve (texto principal para el job, metadata, search_plan serializado).
    """
    normalized_user = user_query.strip()
    if not normalized_user:
        plan = search_plan_from_fallback(".", contact_channels)
        return "", {"fallback": True, "reason": "empty_user_query"}, plan.model_dump_for_job()

    settings = get_settings()
    client = get_llm_client(settings)
    try:
        raw = await client.expand_search_plan(
            user_query=normalized_user,
            contact_channels=contact_channels,
            search_focus=search_focus or "general",
            notes=(notes or "").strip() or None,
        )
        coerced = _coerce_raw_plan(dict(raw), contact_channels)
        if not coerced["main_query"]:
            coerced["main_query"] = normalized_user
        plan = SearchPlan.model_validate(coerced)
        expansion_meta: dict[str, Any] = {
            "model": settings.google_model,
            "focus": search_focus or "general",
            "fallback": False,
            "clarifying_question": plan.clarifying_question,
            "negative_constraints": plan.negative_constraints or None,
        }
        if plan.clarifying_question:
            logger.info(
                "Plan de busqueda sugiere aclaracion (el job puede quedar en espera hasta POST /clarify): %s",
                plan.clarifying_question,
            )
        return plan.main_query.strip(), expansion_meta, plan.model_dump_for_job()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Plan de busqueda con Gemini no disponible, usando fallback: %s", exc)
        plan = search_plan_from_fallback(normalized_user, contact_channels)
        return (
            plan.main_query.strip(),
            {
                "fallback": True,
                "model": settings.google_model,
                "focus": search_focus or "general",
                "error": str(exc)[:240],
            },
            plan.model_dump_for_job(),
        )
