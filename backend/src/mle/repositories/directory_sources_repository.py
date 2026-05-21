from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import DirectorySource


class DirectorySourcesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        directory_id: UUID,
        url: str,
        title: str = "",
        notes: str | None = None,
        source_search_job_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
    ) -> DirectorySource:
        source = DirectorySource(
            directory_id=directory_id,
            url=url.strip(),
            title=title.strip() or "",
            notes=notes.strip() if notes else None,
            status="pending",
            source_search_job_id=source_search_job_id,
            created_by_user_id=created_by_user_id,
        )
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def get_by_id(self, source_id: UUID) -> DirectorySource | None:
        result = await self.session.execute(
            select(DirectorySource).where(DirectorySource.id == source_id)
        )
        return result.scalar_one_or_none()

    async def list_by_directory(
        self,
        directory_id: UUID,
        status: str | None = None,
        limit: int = 100,
    ) -> list[DirectorySource]:
        query = select(DirectorySource).where(
            DirectorySource.directory_id == directory_id,
            DirectorySource.deleted_at.is_(None),
        )
        if status:
            query = query.where(DirectorySource.status == status)
        query = query.order_by(DirectorySource.created_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        source_id: UUID,
        *,
        title: str | None = None,
        notes: str | None = None,
        status: str | None = None,
        scrape_job_id: UUID | None = None,
    ) -> DirectorySource | None:
        source = await self.get_by_id(source_id)
        if source is None:
            return None
        if title is not None:
            source.title = title.strip()
        if notes is not None:
            source.notes = notes.strip() if notes else None
        if status is not None:
            source.status = status
        if scrape_job_id is not None:
            source.scrape_job_id = scrape_job_id
        source.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def delete(self, source_id: UUID, *, deleted_by_user_id: UUID) -> bool:
        source = await self.get_by_id(source_id)
        if source is None or source.deleted_at is not None:
            return False
        now = datetime.now(timezone.utc)
        source.deleted_by = deleted_by_user_id
        source.deleted_at = now
        source.updated_at = now
        self.session.add(source)
        await self.session.commit()
        return True
