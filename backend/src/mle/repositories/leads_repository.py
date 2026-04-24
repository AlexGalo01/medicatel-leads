from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import Lead
from mle.schemas.leads import LeadContacts, LeadRead, LeadsListRead


def _nonempty_text(column: Any) -> Any:
    return and_(column.isnot(None), column != "")


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

    def _contact_filter_clause(self, contact_filter: str | None) -> Any | None:
        if not contact_filter or contact_filter.strip().lower() in ("", "all"):
            return None
        key = contact_filter.strip().lower()
        if key == "linkedin":
            return _nonempty_text(Lead.linkedin_url)
        if key == "whatsapp":
            return _nonempty_text(Lead.whatsapp)
        if key == "email":
            return _nonempty_text(Lead.email)
        if key == "linkedin_and_whatsapp":
            return and_(_nonempty_text(Lead.linkedin_url), _nonempty_text(Lead.whatsapp))
        if key == "has_any":
            return or_(
                _nonempty_text(Lead.email),
                _nonempty_text(Lead.whatsapp),
                _nonempty_text(Lead.linkedin_url),
            )
        return None

    async def list_by_job(
        self,
        job_id: UUID,
        page: int = 1,
        page_size: int = 20,
        min_score: float | None = None,
        name_query: str | None = None,
        contact_filter: str | None = None,
    ) -> LeadsListRead:
        base_query = select(Lead).where(Lead.job_id == job_id)
        count_query = select(func.count(Lead.id)).where(Lead.job_id == job_id)

        if min_score is not None:
            base_query = base_query.where(Lead.score >= min_score)
            count_query = count_query.where(Lead.score >= min_score)

        normalized_name = (name_query or "").strip()
        if normalized_name:
            pattern = f"%{normalized_name}%"
            base_query = base_query.where(Lead.full_name.ilike(pattern))
            count_query = count_query.where(Lead.full_name.ilike(pattern))

        cf_clause = self._contact_filter_clause(contact_filter)
        if cf_clause is not None:
            base_query = base_query.where(cf_clause)
            count_query = count_query.where(cf_clause)

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

    async def get_orm_by_id(self, lead_id: UUID) -> Lead | None:
        return await self.session.get(Lead, lead_id)

    async def update_crm_data(
        self,
        lead_id: UUID,
        crm_stage: str | None = None,
        crm_notes: str | None = None,
        activity_entry: dict[str, str] | None = None,
    ) -> LeadRead | None:
        lead = await self.session.get(Lead, lead_id)
        if lead is None:
            return None

        current_metadata = dict(lead.langsmith_metadata or {})
        current_crm = dict(current_metadata.get("crm", {}))
        current_timeline = list(current_crm.get("activity_timeline", []))

        if crm_stage is not None:
            current_crm["stage"] = crm_stage
        if crm_notes is not None:
            current_crm["notes"] = crm_notes
        if activity_entry is not None:
            current_timeline.append(activity_entry)
            current_crm["activity_timeline"] = current_timeline

        current_metadata["crm"] = current_crm
        lead.langsmith_metadata = current_metadata
        lead.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(lead)
        return self._to_read_model(lead)

    async def apply_field_updates(self, lead_id: UUID, updates: dict[str, Any]) -> Lead | None:
        """Actualiza columnas permitidas y fusiona langsmith_metadata."""
        allowed_columns = {
            "score_reasoning",
            "email",
            "whatsapp",
            "linkedin_url",
            "phone",
            "address",
            "schedule_text",
            "primary_source_url",
            "source_citations",
            "enriched_sources",
        }
        lead = await self.session.get(Lead, lead_id)
        if lead is None:
            return None

        for key, value in updates.items():
            if key in allowed_columns:
                setattr(lead, key, value)

        meta_patch = updates.get("langsmith_metadata")
        if isinstance(meta_patch, dict) and meta_patch:
            meta = dict(lead.langsmith_metadata or {})
            meta.update(meta_patch)
            lead.langsmith_metadata = meta

        lead.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

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
                phone=lead.phone,
                address=lead.address,
                schedule_text=lead.schedule_text,
            ),
            primary_source_url=lead.primary_source_url,
            source_citations=lead.source_citations,
            enriched_sources=lead.enriched_sources or {},
            langsmith_metadata=lead.langsmith_metadata,
            validation_status=lead.validation_status,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        )

