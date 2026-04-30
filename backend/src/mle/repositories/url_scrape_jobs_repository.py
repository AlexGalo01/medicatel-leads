from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import UrlScrapeJob


class UrlScrapeJobsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        target_url: str,
        user_prompt: str,
        directory_id: UUID | None = None,
    ) -> UrlScrapeJob:
        job = UrlScrapeJob(
            target_url=target_url.strip(),
            user_prompt=user_prompt.strip(),
            directory_id=directory_id,
            status="pending",
            progress=0,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_by_id(self, job_id: UUID) -> UrlScrapeJob | None:
        result = await self.session.execute(
            select(UrlScrapeJob).where(UrlScrapeJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        job_id: UUID,
        status: str,
        progress: int,
        metadata_json: dict[str, Any] | None = None,
    ) -> UrlScrapeJob | None:
        job = await self.get_by_id(job_id)
        if job is None:
            return None
        job.status = status
        job.progress = progress
        job.updated_at = datetime.now(timezone.utc)
        if metadata_json is not None:
            job.metadata_json = metadata_json
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def list_by_directory(
        self,
        directory_id: UUID,
        limit: int = 50,
    ) -> list[UrlScrapeJob]:
        result = await self.session.execute(
            select(UrlScrapeJob)
            .where(UrlScrapeJob.directory_id == directory_id)
            .order_by(UrlScrapeJob.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
