from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import DirectoryEntry


class DirectoryEntriesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def bulk_create(self, entries: list[DirectoryEntry]) -> None:
        for entry in entries:
            self.session.add(entry)
        await self.session.commit()

    async def list_by_job(
        self,
        job_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DirectoryEntry], int]:
        base = select(DirectoryEntry).where(DirectoryEntry.job_id == job_id)
        count_q = select(func.count(DirectoryEntry.id)).where(DirectoryEntry.job_id == job_id)
        total_result = await self.session.execute(count_q)
        total = int(total_result.scalar() or 0)
        offset = max(0, (page - 1) * page_size)
        page_query = (
            base.order_by(DirectoryEntry.created_at.asc()).offset(offset).limit(page_size)
        )
        result = await self.session.execute(page_query)
        rows = list(result.scalars().all())
        return rows, total

    async def count_by_job(self, job_id: UUID) -> int:
        count_q = select(func.count(DirectoryEntry.id)).where(DirectoryEntry.job_id == job_id)
        result = await self.session.execute(count_q)
        return int(result.scalar() or 0)
