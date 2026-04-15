from __future__ import annotations

import logging
from uuid import UUID

from mle.db.base import async_session_factory
from mle.orchestration.pipeline import run_lead_pipeline
from mle.repositories.jobs_repository import JobsRepository
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _build_query_text(base_query: str, channels: list[str]) -> str:
    channels_text = ", ".join(channels) if channels else "email, whatsapp, linkedin"
    return f"{base_query} con contacto {channels_text}"


async def run_job_pipeline(job_id: UUID) -> None:
    async with async_session_factory() as session:
        jobs_repository = JobsRepository(session)
        job = await jobs_repository.get_by_id(job_id)
        if job is None:
            logger.error("No se encontro job para ejecutar pipeline job_id=%s", job_id)
            return

        base_query = str(job.metadata_json.get("query_text", "")).strip() or job.specialty
        query_text = _build_query_text(base_query=base_query, channels=job.requested_contact_channels)
        await jobs_repository.update_status(
            job_id=job.id,
            status="running",
            progress=5,
            metadata_json={**job.metadata_json, "query_text": query_text},
        )

    initial_state = LeadSearchGraphState(
        job_id=job_id,
        query_text=query_text,
        status="running",
        current_stage="planner",
        progress=5,
    )
    final_state = await run_lead_pipeline(initial_state)

    if final_state.status != "completed":
        async with async_session_factory() as session:
            jobs_repository = JobsRepository(session)
            current_job = await jobs_repository.get_by_id(job_id)
            metadata_json = current_job.metadata_json if current_job is not None else {}
            await jobs_repository.update_status(
                job_id=job_id,
                status="error",
                progress=final_state.progress,
                metadata_json={
                    **metadata_json,
                    "pipeline_errors": final_state.errors,
                    "pipeline_stage": final_state.current_stage,
                },
            )
        logger.error("Pipeline finalizo con error job_id=%s", job_id)

