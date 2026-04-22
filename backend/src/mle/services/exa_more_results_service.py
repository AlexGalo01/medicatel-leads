from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from mle.clients.exa_client import ExaClient
from mle.core.config import get_settings
from mle.db.base import async_session_factory
from mle.nodes.exa_webset_node import (
    MAX_EXA_RESULTS_PER_CALL,
    _build_search_payload_for_query,
    _extract_results,
)
from mle.nodes.search_finalize_node import MAX_EXA_ACCUMULATED_RAW, _build_exa_preview
from mle.repositories.jobs_repository import JobsRepository
from mle.services.exa_preview_enrich_service import enrich_exa_preview_rows
from mle.services.relevance_filter_service import filter_exa_list_heuristic_only

logger = logging.getLogger(__name__)

_MORE_QUERY_SUFFIXES = (
    "alternativas otras fuentes directorio profesional",
    "perfiles adicionales sitios web medicos",
    "más resultados equipo staff clínica hospital",
    "listado ampliado especialistas mismo perfil",
)


def _normalize_url_key(url: str) -> str:
    return url.strip().lower().rstrip("/")


def _seen_urls_from_raw(raw: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        u = str(item.get("url", "")).strip()
        if u:
            out.add(_normalize_url_key(u))
    return out


def _raw_from_preview_fallback(preview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in preview:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url", "")).strip()
        title = str(row.get("title", "")).strip()
        if url:
            out.append({"url": url, "title": title or url, "highlights": []})
    return out


async def append_exa_results_for_job(job_id: UUID, num_results: int) -> dict[str, Any]:
    """
    Una ronda extra de Exa con consulta variada; solo añade URLs no vistas.
    Solo para jobs en modo demo (presearch_and_search_only) con datos previos.
    """
    n = min(MAX_EXA_RESULTS_PER_CALL, max(1, int(num_results)))
    settings = get_settings()

    async with async_session_factory() as session:
        repo = JobsRepository(session)
        job = await repo.get_by_id(job_id)
        if job is None:
            return {"ok": False, "error": "Job no encontrado"}

        meta = dict(job.metadata_json or {})
        if str(meta.get("pipeline_mode")) != "presearch_and_search_only":
            return {"ok": False, "error": "Cargar más resultados solo está disponible en la vista demo de búsqueda Exa"}

        raw = meta.get("exa_accumulated_raw")
        if not isinstance(raw, list) or not raw:
            preview = meta.get("exa_results_preview")
            if isinstance(preview, list) and preview:
                raw = _raw_from_preview_fallback(preview)
            else:
                return {"ok": False, "error": "No hay resultados Exa previos en este job"}

        seen = _seen_urls_from_raw(raw)

        sp = meta.get("search_plan") if isinstance(meta.get("search_plan"), dict) else {}
        main_q = str(sp.get("main_query") or meta.get("query_text") or "").strip()
        if len(main_q) < 3:
            return {"ok": False, "error": "No se pudo reconstruir la consulta principal del job"}

        exa_cat = sp.get("exa_category")
        if exa_cat not in ("people", "company"):
            exa_cat = "people"

        rounds = int(meta.get("exa_more_rounds", 0) or 0)
        suffix = _MORE_QUERY_SUFFIXES[rounds % len(_MORE_QUERY_SUFFIXES)]
        query = f"{main_q} {suffix}".strip()[:1200]

        minimal_planner: dict[str, Any] = {
            "search_config": {
                "type": settings.exa_search_type,
                "use_highlights": True,
                "exa_category": exa_cat,
                "include_domains": [],
                "exclude_domains": [],
            }
        }
        rel_c = meta.get("relevance_criteria")
        if isinstance(rel_c, dict) and rel_c:
            minimal_planner["relevance_criteria"] = rel_c
        payload = _build_search_payload_for_query(minimal_planner, query, n)
        exa = ExaClient(
            api_key=settings.exa_api_key,
            timeout_seconds=settings.exa_search_timeout_seconds,
        )
        try:
            response = await exa.search(payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Exa cargar-mas fallo job_id=%s: %s", job_id, exc)
            return {"ok": False, "error": f"Exa: {exc!s}"}

        batch = _extract_results(response)
        logger.info(
            "Exa cargar-mas job_id=%s pedidos=%s recibidos=%s urls_ya_vistas=%s",
            job_id,
            n,
            len(batch),
            len(seen),
        )

        new_items: list[dict[str, Any]] = []
        for item in batch:
            if not isinstance(item, dict):
                continue
            u = str(item.get("url", "")).strip()
            if not u:
                continue
            key = _normalize_url_key(u)
            if key in seen:
                continue
            seen.add(key)
            new_items.append(dict(item))

        merged = list(raw) + new_items
        merged = merged[:MAX_EXA_ACCUMULATED_RAW]

        iso = ""
        if isinstance(rel_c, dict):
            iso = str(rel_c.get("country_iso2") or "").strip().upper()
        if len(iso) == 2:
            merged, h_one = filter_exa_list_heuristic_only(merged, iso)
            logger.info(
                "Exa cargar-mas filtro heuristico job_id=%s drops=%s kept=%s",
                job_id,
                h_one.get("relevance_heuristic_only_drops"),
                h_one.get("relevance_heuristic_only_kept"),
            )

        preview = _build_exa_preview(merged)
        try:
            preview = await enrich_exa_preview_rows(preview)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Enriquecimiento preview tras cargar mas omitido job_id=%s: %s", job_id, exc)

        meta["exa_accumulated_raw"] = merged
        meta["exa_results_preview"] = preview
        meta["exa_more_rounds"] = rounds + 1
        meta["sources_visited"] = len(merged)
        meta["leads_extracted"] = len(merged)
        meta["exa_last_more_at"] = datetime.now(timezone.utc).isoformat()

        await repo.update_status(
            job_id=job_id,
            status=job.status,
            progress=job.progress,
            metadata_json=meta,
        )

        return {
            "ok": True,
            "added_count": len(new_items),
            "total_count": len(merged),
            "preview_count": len(preview),
            "query_used": query,
        }
