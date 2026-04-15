from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import Lead
from mle.schemas.leads import LeadContacts, LeadRead, LeadsListRead


class LeadsRepository:
    """Async repository for lead persistence and reads."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, lead: Lead) -> Lead:
        self.session.add(lead)
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

    async def update_score(self, lead_id: UUID, score: float, score_reasoning: str) -> Lead | None:
        lead = await self.session.get(Lead, lead_id)
        if lead is None:
            return None

        lead.score = score
        lead.score_reasoning = score_reasoning
        lead.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

    async def list_by_job(
        self, job_id: UUID, page: int = 1, page_size: int = 20, min_score: float | None = None
    ) -> LeadsListRead:
        base_query = select(Lead).where(Lead.job_id == job_id)
        count_query = select(func.count(Lead.id)).where(Lead.job_id == job_id)

        if min_score is not None:
            base_query = base_query.where(Lead.score >= min_score)
            count_query = count_query.where(Lead.score >= min_score)

        total_result = await self.session.execute(count_query)
        total = int(total_result.scalar_one())

        offset = (page - 1) * page_size
        data_query = base_query.order_by(Lead.score.desc()).offset(offset).limit(page_size)
        rows = await self.session.execute(data_query)
        leads = rows.scalars().all()

        items = [self._to_read_model(lead) for lead in leads]
        return LeadsListRead(items=items, page=page, page_size=page_size, total=total)

    async def get_by_id(self, lead_id: UUID) -> LeadRead | None:
        lead = await self.session.get(Lead, lead_id)
        if lead is None:
            return None
        return self._to_read_model(lead)

    def _to_read_model(self, lead: Lead) -> LeadRead:
        return LeadRead(
            id=lead.id,
            job_id=lead.job_id,
            full_name=lead.full_name,
            specialty=lead.specialty,
            country=lead.country,
            city=lead.city,
            organization_name=lead.organization_name,
            score=lead.score,
            score_reasoning=lead.score_reasoning,
            contacts=LeadContacts(
                email=lead.email,
                whatsapp=lead.whatsapp,
                linkedin_url=lead.linkedin_url,
            ),
            primary_source_url=lead.primary_source_url,
            validation_status=lead.validation_status,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        )

