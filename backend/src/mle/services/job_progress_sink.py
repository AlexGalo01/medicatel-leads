from __future__ import annotations

import logging
from uuid import UUID

from mle.db.base import async_session_factory
from mle.repositories.jobs_repository import JobsRepository
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _db_status_from_state(state: LeadSearchGraphState) -> str:
    if state.status == "error":
        return "error"
    if state.current_stage == "done" and state.progress >= 100:
        return "completed"
    return "running"


async def persist_pipeline_progress(job_id: UUID, state: LeadSearchGraphState) -> None:
    """Persiste progreso, etapa y métricas parciales para que el polling del cliente refleje el avance real."""
    try:
        async with async_session_factory() as session:
            jobs_repository = JobsRepository(session)
            job = await jobs_repository.get_by_id(job_id)
            if job is None:
                return

            base_meta: dict[str, object] = dict(job.metadata_json or {})
            base_meta["pipeline_stage"] = state.current_stage

            n_exa = len(state.exa_raw_results)
            if n_exa > 0:
                base_meta["sources_visited"] = n_exa
                base_meta["leads_extracted"] = n_exa

            # Tras `done`, `storage_export_node` ya fijó `stored_leads` con el conteo filtrado; no pisar con len(state.leads).
            if state.leads and state.current_stage != "done":
                base_meta["stored_leads"] = len(state.leads)

            base_meta["contact_coverage"] = round(float(state.contact_coverage), 4)
            base_meta["missing_contact_count"] = int(state.missing_contact_count)
            base_meta["retry_used"] = bool(state.retry_used)
            base_meta["discarded_leads_count"] = len(state.discarded_leads)

            await jobs_repository.update_status(
                job_id=job_id,
                status=_db_status_from_state(state),
                progress=int(state.progress),
                metadata_json=base_meta,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo persistir progreso intermedio job_id=%s: %s", job_id, exc)
