from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import SearchJob


class JobsRepository:
    """Async repository for search job persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        specialty: str,
        country: str,
        city: str,
        requested_contact_channels: list[str],
        notes: str | None = None,
    ) -> SearchJob:
        job = SearchJob(
            specialty=specialty,
            country=country,
            city=city,
            status="pending",
            progress=0,
            requested_contact_channels=requested_contact_channels,
            notes=notes,
            metadata_json={},
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_by_id(self, job_id: UUID) -> SearchJob | None:
        query = select(SearchJob).where(SearchJob.id == job_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        job_id: UUID,
        status: str,
        progress: int,
        metadata_json: dict[str, object] | None = None,
    ) -> SearchJob | None:
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

