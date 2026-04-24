"""Nodo de auto-enriquecimiento: corre Exa /contents + OpenCLI + Gemini por cada preview en paralelo.

Reemplaza el botón manual "Enriquecer" — el pipeline entrega los resultados ya con
teléfono, dirección, horario, email, WhatsApp y LinkedIn extraídos desde la primera búsqueda.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from langsmith import traceable

from sqlalchemy.dialects.postgresql import insert as pg_insert

from mle.clients.exa_client import ExaClient
from mle.clients.opencli_client import OpenCliClient
from mle.clients.llm_factory import get_llm_client, get_reviewer_llm_client
from mle.core.config import effective_exa_search_timeout_seconds, get_settings
from mle.db.base import async_session_factory
from mle.db.models import Opportunity
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.repositories.directories_repository import DirectoriesRepository
from mle.repositories.jobs_repository import JobsRepository
from mle.services.lead_deep_enrich_service import (
    EnrichmentResult,
    LeadCore,
    enrich_lead_contacts,
)
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _preview_to_core(preview: dict[str, Any], country: str, entity_type: str = "person") -> LeadCore:
    return LeadCore(
        full_name=str(preview.get("title") or "").strip(),
        specialty=str(preview.get("specialty") or "").strip(),
        city=str(preview.get("city") or "").strip(),
        country=country,
        entity_type=entity_type,
        primary_source_url=str(preview.get("url") or "").strip(),
    )


async def _create_opportunities_for_directory(job_id, enriched_items: list[dict[str, Any]]) -> int:
    """Crea Opps en el directorio del job, una por cada preview item enriquecido.

    Degrade-safe: si el job no tiene directorio asociado, retorna 0 sin tumbar el pipeline.
    """
    if not enriched_items:
        return 0
    now = datetime.now(timezone.utc)
    created = 0
    try:
        async with async_session_factory() as session:
            jobs_repo = JobsRepository(session)
            job = await jobs_repo.get_by_id(job_id)
            if job is None or job.directory_id is None:
                logger.info("auto_enrich job_id=%s sin directorio asociado — skip creación de Opps", job_id)
                return 0
            dirs_repo = DirectoriesRepository(session)
            first_step = await dirs_repo.first_step(job.directory_id)
            if first_step is None:
                logger.warning("auto_enrich job_id=%s directorio sin steps — skip", job_id)
                return 0
            rows: list[dict[str, Any]] = []
            for item in enriched_items:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()[:500]
                url = str(item.get("url") or "").strip()[:2000]
                if not title and not url:
                    continue
                contacts: list[dict[str, Any]] = []
                for kind in ("email", "whatsapp", "phone", "linkedin_url", "website", "facebook_url", "instagram_url"):
                    val = str(item.get(kind) or "").strip()
                    if not val:
                        continue
                    mapped_kind = "linkedin" if kind == "linkedin_url" else kind
                    contacts.append(
                        {
                            "id": f"auto-{mapped_kind}-{len(contacts)}",
                            "kind": mapped_kind,
                            "value": val[:500],
                            "note": None,
                            "role": None,
                            "is_primary": len(contacts) == 0,
                        }
                    )
                rows.append({
                    "id": uuid4(),
                    "directory_id": job.directory_id,
                    "current_step_id": first_step.id,
                    "job_id": job_id,
                    "exa_preview_index": item.get("index"),
                    "title": title or url,
                    "source_url": url,
                    "snippet": str(item.get("snippet") or "").strip()[:4000] or None,
                    "specialty": str(item.get("specialty") or "").strip()[:160],
                    "city": str(item.get("city") or "").strip()[:120],
                    "stage": "first_contact",
                    "contacts": contacts,
                    "activity_timeline": [
                        {
                            "at": now.isoformat(),
                            "stage": first_step.name,
                            "author": "sistema",
                            "text": "Oportunidad creada automáticamente desde búsqueda Exa + auto-enrich.",
                        }
                    ],
                    "profile_overrides": {},
                    "created_at": now,
                    "updated_at": now,
                })

            if rows:
                stmt = pg_insert(Opportunity).values(rows)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["job_id", "exa_preview_index"],
                )
                result = await session.execute(stmt)
                await session.commit()
                created = result.rowcount
    except Exception as exc:  # noqa: BLE001
        logger.warning("auto_enrich: creación de Opps falló job_id=%s: %s", job_id, exc)
    return created


def _apply_enrichment_to_preview(preview: dict[str, Any], enr: EnrichmentResult) -> dict[str, Any]:
    """Fusiona el EnrichmentResult en el dict de preview sin sobrescribir lo que ya tenía."""
    out = dict(preview)
    for field_name in (
        "email",
        "whatsapp",
        "phone",
        "address",
        "schedule_text",
        "linkedin_url",
        "website",
        "facebook_url",
        "instagram_url",
    ):
        incoming = getattr(enr, field_name, "")
        if incoming and not (out.get(field_name) or "").strip():
            out[field_name] = incoming
    if enr.description and not (out.get("description") or "").strip():
        out["description"] = enr.description
    if enr.enriched_sources:
        existing = out.get("enriched_sources") or {}
        if not isinstance(existing, dict):
            existing = {}
        existing.update(enr.enriched_sources)
        out["enriched_sources"] = existing
    out["enrichment_status"] = enr.status
    if enr.message:
        out["enrichment_message"] = enr.message
    return out


@traceable(
    name="auto_enrich_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def auto_enrich_node(state: LeadSearchGraphState) -> dict[str, object]:
    """Enriquece cada item del preview con Exa + OpenCLI en paralelo (semáforo de concurrencia)."""
    try:
        settings = get_settings()
        meta = dict(state.langsmith_metadata or {})
        preview_items = meta.get("exa_results_preview") or []
        if not isinstance(preview_items, list) or not preview_items:
            logger.info("auto_enrich job_id=%s sin preview — skip", state.job_id)
            return {
                "status": "completed",
                "current_stage": "done",
                "progress": 100,
                "langsmith_metadata": {**meta, "auto_enrich_skipped": "sin_preview"},
            }

        planner_out = state.planner_output if isinstance(state.planner_output, dict) else {}
        rel = planner_out.get("relevance_criteria") if isinstance(planner_out.get("relevance_criteria"), dict) else {}
        country = str(rel.get("country_text") or rel.get("country_iso2") or "").strip()

        # Determinar entity_type desde la categoría de búsqueda Exa
        search_config = planner_out.get("search_config") or {}
        exa_category = str(search_config.get("exa_category") or "").strip().lower()
        entity_type = "company" if exa_category == "company" else "person"

        exa_client = ExaClient(
            api_key=settings.exa_api_key,
            timeout_seconds=effective_exa_search_timeout_seconds(settings),
        )
        opencli = OpenCliClient(settings)
        proposer = get_llm_client(settings)
        reviewer = get_reviewer_llm_client(settings)

        semaphore = asyncio.Semaphore(max(1, int(settings.auto_enrich_concurrency)))

        async def _enrich_one(item: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(item, dict):
                return item
            async with semaphore:
                try:
                    prefetched_maps = item.pop("_prefetched_maps", None)
                    core = _preview_to_core(item, country, entity_type)
                    if not core.full_name and not core.primary_source_url:
                        return item
                    enr = await enrich_lead_contacts(
                        core,
                        exa_client=exa_client,
                        opencli=opencli,
                        proposer=proposer,
                        reviewer=reviewer,
                        settings=settings,
                        prefetched_maps=prefetched_maps,
                    )
                    return _apply_enrichment_to_preview(item, enr)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("auto_enrich item fallo (degrade safe) url=%s: %s", item.get("url"), exc)
                    out = dict(item)
                    out["enrichment_status"] = "error"
                    out["enrichment_message"] = str(exc)[:240]
                    return out

        enriched = await asyncio.gather(*[_enrich_one(item) for item in preview_items])

        enriched_count = sum(1 for it in enriched if isinstance(it, dict) and it.get("enrichment_status") == "enriched")
        logger.info(
            "auto_enrich job_id=%s total=%s enriquecidos=%s concurrencia=%s",
            state.job_id,
            len(enriched),
            enriched_count,
            settings.auto_enrich_concurrency,
        )

        # Crear Opportunities en el directorio del job (step inicial).
        opps_created = await _create_opportunities_for_directory(state.job_id, enriched)

        return {
            "status": "completed",
            "current_stage": "done",
            "progress": 100,
            "langsmith_metadata": {
                **meta,
                "exa_results_preview": enriched,
                "auto_enrich": {
                    "total": len(enriched),
                    "enriched": enriched_count,
                    "opportunities_created": opps_created,
                    "concurrency": settings.auto_enrich_concurrency,
                },
            },
        }
    except Exception as exc:  # noqa: BLE001
        error_message = f"auto_enrich_node fallo: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "completed",  # no tumbamos el job: el preview ya existe sin enrich
            "current_stage": "done",
            "progress": 100,
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "auto_enrich_error": error_message,
                "auto_enrich_state_snapshot": asdict(state),
            },
        }
