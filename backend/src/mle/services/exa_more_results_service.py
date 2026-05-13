from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from mle.clients.brave_client import BraveSearchClient
from mle.clients.exa_client import ExaClient
from mle.clients.llm_factory import get_llm_client
from mle.core.config import effective_exa_search_timeout_seconds, get_settings
from mle.db.base import async_session_factory
from mle.nodes.exa_webset_node import (
    MAX_EXA_RESULTS_PER_CALL,
    _build_search_payload_for_query,
    _extract_results,
)
from mle.nodes.search_finalize_node import MAX_EXA_ACCUMULATED_RAW, _build_exa_preview
from mle.repositories.jobs_repository import JobsRepository
from mle.services.exa_preview_enrich_service import enrich_exa_preview_rows
from mle.services.relevance_filter_service import (
    filter_exa_list_heuristic_only,
    filter_exa_raw_results_by_relevance,
)

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
    logger.info("append_exa_results_for_job iniciado: job_id=%s, num_results=%s", job_id, num_results)
    n = min(MAX_EXA_RESULTS_PER_CALL, max(1, int(num_results)))
    settings = get_settings()

    async with async_session_factory() as session:
        repo = JobsRepository(session)
        job = await repo.get_by_id(job_id)
        if job is None:
            logger.error("Job no encontrado: job_id=%s", job_id)
            return {"ok": False, "error": "Job no encontrado"}

        meta = dict(job.metadata_json or {})
        if str(meta.get("pipeline_mode")) != "presearch_and_search_only":
            logger.error("pipeline_mode incorrecto: job_id=%s, mode=%s", job_id, meta.get("pipeline_mode"))
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
        iso = str((rel_c or {}).get("country_iso2") or "").strip().upper()
        payload = _build_search_payload_for_query(minimal_planner, query, n)

        # --- Ejecutar Exa + Brave en paralelo ---
        exa = ExaClient(
            api_key=settings.exa_api_key,
            timeout_seconds=effective_exa_search_timeout_seconds(settings),
        )
        exa_coro = exa.search(payload)

        brave_coros: list[Any] = []
        if settings.brave_search_enabled and settings.brave_search_api_key:
            brave_client = BraveSearchClient(
                api_key=settings.brave_search_api_key,
                timeout_seconds=settings.brave_search_timeout_seconds,
            )
            brave_country = iso if len(iso) == 2 else None
            brave_coros.append(brave_client.web_search(main_q, country=brave_country, count=20, pages=3))
            if exa_cat == "people":
                brave_coros.append(brave_client.web_search(f"site:linkedin.com/in {main_q}", country=brave_country, count=20, pages=2))

        logger.info("Llamando a EXA + %d Brave queries: job_id=%s", len(brave_coros), job_id)
        all_outcomes = await asyncio.gather(exa_coro, *brave_coros, return_exceptions=True)
        exa_outcome = all_outcomes[0]
        brave_outcomes = all_outcomes[1:]

        # Procesar Exa
        exa_failed = False
        batch: list[dict[str, Any]] = []
        if isinstance(exa_outcome, Exception):
            logger.warning("Exa cargar-mas fallo job_id=%s: %s", job_id, exa_outcome)
            exa_failed = True
        else:
            batch = _extract_results(exa_outcome)
            logger.info("EXA exitoso: job_id=%s, resultados=%s", job_id, len(batch))

        # Procesar Brave
        for bi, brave_outcome in enumerate(brave_outcomes):
            if isinstance(brave_outcome, Exception):
                logger.warning("Brave cargar-mas query %s fallo job_id=%s: %s", bi, job_id, brave_outcome)
            elif isinstance(brave_outcome, list):
                logger.info("Brave cargar-mas query %s: %d resultados job_id=%s", bi, len(brave_outcome), job_id)
                batch.extend(brave_outcome)

        if not batch:
            error_detail = f"Exa: {exa_outcome!s}" if exa_failed else "Sin resultados de ninguna fuente"
            return {"ok": False, "error": error_detail}

        # Warning si Exa falló pero Brave trajo resultados
        if exa_failed and batch:
            existing_warnings = list(meta.get("warnings", []))
            existing_warnings.append(
                "La fuente principal (Exa) no está disponible. "
                "Resultados adicionales provienen de Brave Search."
            )
            meta["warnings"] = existing_warnings

        logger.info("Extrayendo resultados combinados: job_id=%s, batch_size=%s", job_id, len(batch))

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

        # Apply LLM-based sector relevance filter to new items
        llm_metadata: dict = {}
        if new_items and isinstance(rel_c, dict):
            llm = get_llm_client(settings)
            try:
                filtered_new, llm_metadata = await filter_exa_raw_results_by_relevance(
                    raw_results=new_items,
                    user_query=main_q,
                    relevance_criteria=rel_c,
                    gemini_client=llm,
                )

                # Log detallado de LLM filtering decisions
                logger.info("=" * 80)
                logger.info("LLM RELEVANCE FILTER — sector/profesion objetivo: %s", rel_c.get("role_or_stack_hint", main_q))
                logger.info("=" * 80)
                kept_set = {str(item.get("url", "")).strip().lower().rstrip("/") for item in filtered_new}
                for item in new_items:
                    url = str(item.get("url", "")).strip()
                    title = str(item.get("title", "")).strip()
                    url_key = url.lower().rstrip("/")
                    status = "✓ KEPT" if url_key in kept_set else "✗ DROPPED"
                    logger.info(
                        "%s | %s | %s",
                        status,
                        title[:60],
                        url[:70],
                    )
                logger.info("=" * 80)
                logger.info(
                    "LLM Filter Summary: total=%s, kept=%s, dropped=%s",
                    len(new_items),
                    llm_metadata.get("relevance_filter_kept", 0),
                    llm_metadata.get("relevance_filter_dropped", 0),
                )

                # Replace merged list: remove the new_items that didn't pass LLM filter
                merged = [
                    item for item in merged
                    if str(item.get("url", "")).strip().lower().rstrip("/") in kept_set
                    or item in raw  # Keep all items from the original raw list
                ]
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Exa cargar-mas LLM relevance filter omitido job_id=%s: %s",
                    job_id,
                    exc,
                    exc_info=True,
                )

        # Build preview: keep existing enriched rows + only enrich the new items
        existing_preview: list[dict[str, Any]] = list(meta.get("exa_results_preview") or [])
        existing_preview_urls = {
            _normalize_url_key(str(r.get("url", "")))
            for r in existing_preview
            if isinstance(r, dict) and r.get("url")
        }

        # Items that passed the filter and are genuinely new
        new_kept_urls = {
            _normalize_url_key(str(item.get("url", "")))
            for item in merged
            if _normalize_url_key(str(item.get("url", ""))) not in existing_preview_urls
        }
        new_raw_for_preview = [
            item for item in merged
            if _normalize_url_key(str(item.get("url", ""))) in new_kept_urls
        ]

        logger.info("Construyendo preview solo para nuevos items: job_id=%s, new_count=%s", job_id, len(new_raw_for_preview))
        new_preview_rows = _build_exa_preview(new_raw_for_preview)

        if new_preview_rows:
            try:
                new_preview_rows = await enrich_exa_preview_rows(new_preview_rows)
                logger.info("Preview nuevos enriquecido: job_id=%s, items=%s", job_id, len(new_preview_rows))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Enriquecimiento preview nuevos omitido job_id=%s: %s", job_id, exc, exc_info=True)

        preview = existing_preview + new_preview_rows
        logger.info("Preview total: job_id=%s, items=%s (existing=%s + new=%s)", job_id, len(preview), len(existing_preview), len(new_preview_rows))

        logger.info("Guardando metadata actualizada: job_id=%s", job_id)
        meta["exa_accumulated_raw"] = merged
        meta["exa_results_preview"] = preview
        meta["exa_more_rounds"] = rounds + 1
        # Acumular LPA de esta ronda
        new_lpa: list = llm_metadata.get("lpa_results") or []
        if new_lpa:
            existing_lpa: list = meta.get("lpa_results") or []
            existing_lpa_urls = {str(x.get("url", "")).strip().lower() for x in existing_lpa}
            for item in new_lpa:
                if str(item.get("url", "")).strip().lower() not in existing_lpa_urls:
                    existing_lpa.append(item)
            meta["lpa_results"] = existing_lpa
            meta["lpa_count"] = len(existing_lpa)
            meta["lpa_preview"] = _build_exa_preview(existing_lpa)
        meta["sources_visited"] = len(merged)
        meta["leads_extracted"] = len(merged)
        meta["exa_last_more_at"] = datetime.now(timezone.utc).isoformat()

        await repo.update_status(
            job_id=job_id,
            status=job.status,
            progress=job.progress,
            metadata_json=meta,
        )
        logger.info(
            "append_exa_results_for_job completado: job_id=%s, added=%s, total=%s, preview=%s",
            job_id,
            len(new_items),
            len(merged),
            len(preview),
        )

        return {
            "ok": True,
            "added_count": len(new_items),
            "total_count": len(merged),
            "preview_count": len(preview),
            "query_used": query,
        }
