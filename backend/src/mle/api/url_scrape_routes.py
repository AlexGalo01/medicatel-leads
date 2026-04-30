from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from mle.api.deps import get_current_user, require_permission
from mle.api.schemas import (
    UrlScrapeJobCreateRequest,
    UrlScrapeJobStatusResponse,
    UrlScrapeJobsListResponse,
    UrlScrapeJobListItemResponse,
    UrlScrapeJobPushRequest,
    UrlScrapeResultPreviewItem,
)
from mle.db.base import async_session_factory
from mle.db.models import User, Opportunity, DirectoryStep
from mle.repositories.url_scrape_jobs_repository import UrlScrapeJobsRepository
from mle.repositories.opportunities_repository import OpportunitiesRepository
from mle.repositories.directories_repository import DirectoriesRepository
from mle.services.url_scrape_service import run_url_scrape_pipeline

logger = logging.getLogger(__name__)

url_scrape_router = APIRouter(prefix="/url-scrape-jobs", tags=["url-scraper"])


@url_scrape_router.post("", status_code=202)
async def create_url_scrape_job(
    payload: UrlScrapeJobCreateRequest,
    _u: User = Depends(require_permission("use_search")),
) -> UrlScrapeJobStatusResponse:
    """Crea un nuevo job de scraping de URL."""
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        job = await repo.create(
            target_url=payload.target_url,
            user_prompt=payload.user_prompt,
            directory_id=payload.directory_id,
        )
        job_id = job.id
        created_at = job.created_at
        updated_at = job.updated_at

    asyncio.create_task(run_url_scrape_pipeline(job_id))

    return UrlScrapeJobStatusResponse(
        job_id=str(job_id),
        status="pending",
        progress=0,
        target_url=payload.target_url,
        entries_count=0,
        scrape_results_preview=[],
        error_message=None,
        created_at=created_at,
        updated_at=updated_at,
    )


@url_scrape_router.get("/{job_id}", response_model=UrlScrapeJobStatusResponse)
async def get_url_scrape_job(
    job_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> UrlScrapeJobStatusResponse:
    """Obtiene el estado y preview de un URL scrape job."""
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        job = await repo.get_by_id(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="URL scrape job no encontrado")

    meta = job.metadata_json if isinstance(job.metadata_json, dict) else {}
    preview_raw = meta.get("scrape_results_preview") or []
    error_msg = meta.get("error") if job.status == "error" else None

    # Convert preview items to UrlScrapeResultPreviewItem
    preview: list[UrlScrapeResultPreviewItem] = []
    if isinstance(preview_raw, list):
        for item in preview_raw:
            if isinstance(item, dict):
                preview.append(
                    UrlScrapeResultPreviewItem(
                        index=item.get("index", 0),
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("snippet"),
                        city=item.get("city", ""),
                        phones=item.get("phones", []),
                        emails=item.get("emails", []),
                    )
                )

    return UrlScrapeJobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress,
        target_url=job.target_url,
        directory_id=str(job.directory_id) if job.directory_id else None,
        entries_count=int(meta.get("entries_count", len(preview))),
        scrape_results_preview=preview,
        error_message=str(error_msg) if error_msg else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@url_scrape_router.get("", response_model=UrlScrapeJobsListResponse)
async def list_url_scrape_jobs(
    directory_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _u: User = Depends(require_permission("use_search")),
) -> UrlScrapeJobsListResponse:
    """Lista los URL scrape jobs, opcionalmente filtrados por directorio."""
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        if directory_id:
            jobs = await repo.list_by_directory(directory_id=directory_id, limit=limit)
        else:
            jobs = []

    items = [
        UrlScrapeJobListItemResponse(
            job_id=str(j.id),
            target_url=j.target_url,
            status=j.status,
            entries_count=int((j.metadata_json or {}).get("entries_count", 0)),
            created_at=j.created_at,
        )
        for j in jobs
    ]
    return UrlScrapeJobsListResponse(items=items)


@url_scrape_router.post("/{job_id}/cancel", status_code=200)
async def cancel_url_scrape_job(
    job_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> dict[str, str]:
    """Cancela un URL scrape job en ejecución."""
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        job = await repo.get_by_id(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="URL scrape job no encontrado")
        if job.status not in ("pending", "running"):
            raise HTTPException(status_code=409, detail="Solo se pueden cancelar jobs pendientes o en ejecución")

        await repo.update_status(job_id, "cancelled", job.progress)

    return {"status": "cancelled", "job_id": str(job_id)}


@url_scrape_router.post("/{job_id}/push-to-directory", status_code=201)
async def push_entries_to_directory(
    job_id: UUID,
    payload: UrlScrapeJobPushRequest,
    current: User = Depends(require_permission("manage_opportunities")),
) -> dict[str, int | str]:
    """Empuja las entradas extraídas al directorio como Opportunities."""
    async with async_session_factory() as session:
        repo = UrlScrapeJobsRepository(session)
        job = await repo.get_by_id(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="URL scrape job no encontrado")
        if job.status != "completed":
            raise HTTPException(status_code=409, detail="El job aún no está completado")

        dirs_repo = DirectoriesRepository(session)
        directory = await dirs_repo.get(payload.directory_id)
        if directory is None:
            raise HTTPException(status_code=404, detail="Directorio no encontrado")

        # Get first step of target directory
        steps = await dirs_repo.list_steps(payload.directory_id)
        first_step = min(steps, key=lambda s: s.display_order) if steps else None

        # Get preview from metadata
        meta = job.metadata_json if isinstance(job.metadata_json, dict) else {}
        preview_raw = meta.get("scrape_results_preview") or []

        # Build index set to filter by
        indices_set = set(payload.entry_indices) if payload.entry_indices else None

        # Create opportunities from preview items
        created_opps = 0
        opp_repo = OpportunitiesRepository(session)

        if isinstance(preview_raw, list):
            for i, preview_item in enumerate(preview_raw):
                # Filter by index if specified
                if indices_set is not None and (i + 1) not in indices_set:
                    continue
                if not isinstance(preview_item, dict):
                    continue

                title = preview_item.get("title", "")
                url = preview_item.get("url", "")
                snippet = preview_item.get("snippet")
                city = preview_item.get("city", "")
                phones = preview_item.get("phones", [])
                emails = preview_item.get("emails", [])

                # Build contacts list
                contacts = []
                for j, phone in enumerate(phones or []):
                    contacts.append(
                        {
                            "kind": "phone",
                            "value": phone,
                            "is_primary": j == 0,
                        }
                    )
                for email in emails or []:
                    contacts.append(
                        {
                            "kind": "email",
                            "value": email,
                            "is_primary": False,
                        }
                    )

                opp = Opportunity(
                    directory_id=payload.directory_id,
                    current_step_id=first_step.id if first_step else None,
                    job_id=None,
                    title=title or url[:120] or "(sin título)",
                    source_url=url,
                    snippet=snippet,
                    city=city,
                    owner_user_id=current.id,
                    contacts=contacts,
                )
                session.add(opp)
                created_opps += 1

        await session.commit()

    return {"created": created_opps, "directory_id": str(payload.directory_id)}
