from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import SearchJob


class JobsRepository:
    """Async repository for search job persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        expanded_query_text: str,
        requested_contact_channels: list[str],
        notes: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> SearchJob:
        normalized_query = expanded_query_text.strip()
        meta = dict(metadata_json or {})
        meta.setdefault("query_text", normalized_query)
        job = SearchJob(
            specialty=normalized_query[:120] or "Busqueda general",
            country="Global",
            city="Global",
            status="pending",
            progress=0,
            requested_contact_channels=requested_contact_channels,
            notes=notes,
            metadata_json=meta,
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

    async def list_jobs(
        self,
        *,
        limit: int | None = 15,
        offset: int = 0,
        query_text: str | None = None,
    ) -> tuple[list[SearchJob], int]:
        base_query = select(SearchJob)
        normalized = (query_text or "").strip()
        if normalized:
            pattern = f"%{normalized}%"
            base_query = base_query.where(
                or_(
                    SearchJob.specialty.ilike(pattern),
                    SearchJob.metadata_json["user_query"].as_string().ilike(pattern),
                    SearchJob.metadata_json["query_text"].as_string().ilike(pattern),
                )
            )
        total_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(total_query)
        total = int(total_result.scalar_one() or 0)

        query = base_query.order_by(SearchJob.created_at.desc()).offset(max(0, offset))
        if limit is not None:
            query = query.limit(max(1, min(limit, 5000)))

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

