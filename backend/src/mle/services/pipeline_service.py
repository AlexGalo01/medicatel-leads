from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from langsmith import traceable

from mle.db.base import async_session_factory
from mle.observability.langsmith_setup import configure_langsmith_env, trace_inputs_job_id
from mle.orchestration.pipeline import run_lead_pipeline
from mle.repositories.jobs_repository import JobsRepository
from mle.repositories.scraping_sites_repository import ScrapingSitesRepository
from mle.repositories.url_scrape_jobs_repository import UrlScrapeJobsRepository
from mle.services.url_scrape_service import run_url_scrape_pipeline
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _build_query_text(base_query: str) -> str:
    return base_query


@traceable(name="search_job_pipeline", run_type="chain", process_inputs=trace_inputs_job_id)
async def run_job_pipeline(job_id: UUID) -> None:
    configure_langsmith_env()
    async with async_session_factory() as session:
        jobs_repository = JobsRepository(session)
        job = await jobs_repository.get_by_id(job_id)
        if job is None:
            logger.error("No se encontro job para ejecutar pipeline job_id=%s", job_id)
            return

        raw_plan = job.metadata_json.get("search_plan")
        search_plan: dict[str, object] = dict(raw_plan) if isinstance(raw_plan, dict) else {}

        base_query = str(job.metadata_json.get("query_text", "")).strip() or job.specialty
        query_text = _build_query_text(base_query=base_query)
        await jobs_repository.update_status(
            job_id=job.id,
            status="running",
            progress=5,
            metadata_json={**job.metadata_json, "query_text": query_text},
        )

        # Launch scraping sites in parallel if specified
        scraping_jobs: list[UUID] = []
        if job.scraping_site_ids:
            sites_repo = ScrapingSitesRepository(session)
            url_jobs_repo = UrlScrapeJobsRepository(session)
            for site_id in job.scraping_site_ids:
                site = await sites_repo.get(site_id)
                if not site:
                    logger.warning("Scraping site not found site_id=%s", site_id)
                    continue
                prompt = site.scrape_prompt or f"Extraer profesionales y entidades del directorio: {site.title or site.url}"
                scrape_job = await url_jobs_repo.create(
                    target_url=site.url,
                    user_prompt=prompt,
                    directory_id=job.directory_id,
                )
                # Mark as auto_push so results are pushed automatically
                scrape_job.auto_push = True
                session.add(scrape_job)
                scraping_jobs.append(scrape_job.id)
                logger.info("Created scraping job for site_id=%s scrape_job_id=%s", site_id, scrape_job.id)
            if scraping_jobs:
                await session.commit()
                # Launch all scraping jobs concurrently (non-blocking)
                for scrape_job_id in scraping_jobs:
                    asyncio.create_task(run_url_scrape_pipeline(scrape_job_id))

    initial_state = LeadSearchGraphState(
        job_id=job_id,
        query_text=query_text,
        status="running",
        current_stage="planner",
        progress=5,
        search_plan=search_plan,
    )
    final_state = await run_lead_pipeline(initial_state)

    # Si hay errores en el pipeline, marcar como error
    if final_state.status == "error" or final_state.errors:
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
        logger.error("Pipeline finalizo con error job_id=%s: %s", job_id, final_state.errors)
    else:
        # Pipeline exitoso (sin errores)
        async with async_session_factory() as session:
            jobs_repository = JobsRepository(session)
            current_job = await jobs_repository.get_by_id(job_id)
            metadata_json = current_job.metadata_json if current_job is not None else {}
            await jobs_repository.update_status(
                job_id=job_id,
                status="completed",
                progress=100,
                metadata_json={
                    **metadata_json,
                    "pipeline_stage": "done",
                },
            )
        logger.info("Pipeline completado exitosamente job_id=%s", job_id)

