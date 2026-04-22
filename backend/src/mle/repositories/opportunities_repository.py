from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.db.models import Opportunity, SearchJob
from mle.schemas.opportunities import (
    CONTACT_KIND_KEYS,
    DEFAULT_OPPORTUNITY_STAGE,
    OPPORTUNITY_STAGE_KEYS,
    RESPONSE_OUTCOME_KEYS,
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_preview_row(job: SearchJob, exa_preview_index: int) -> dict[str, Any] | None:
    raw = job.metadata_json.get("exa_results_preview")
    if not isinstance(raw, list):
        return None
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index", 0))
        except (TypeError, ValueError):
            continue
        if idx == exa_preview_index:
            return item
    return None


_MAX_PROFILE_ABOUT = 8000
_MAX_PROFILE_LOCATION = 500
_MAX_PROFILE_EXPERIENCES = 24


def _normalize_experience_row(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        d = raw
    elif hasattr(raw, "model_dump"):
        d = raw.model_dump()
    else:
        d = {}
    role = str(d.get("role", "")).strip()[:300]
    org_raw = str(d.get("organization", "")).strip()[:300]
    period_raw = str(d.get("period", "")).strip()[:200]
    return {
        "role": role,
        "organization": org_raw or None,
        "period": period_raw or None,
    }


def apply_profile_overrides_patch(current: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    po = dict(current) if isinstance(current, dict) else {}
    for key, value in updates.items():
        if key == "about":
            if value is None:
                po.pop("about", None)
            else:
                po["about"] = str(value).strip()[:_MAX_PROFILE_ABOUT]
        elif key == "location":
            if value is None:
                po.pop("location", None)
            else:
                po["location"] = str(value).strip()[:_MAX_PROFILE_LOCATION]
        elif key == "experiences":
            if value is None:
                po.pop("experiences", None)
            elif isinstance(value, list):
                po["experiences"] = [_normalize_experience_row(x) for x in value[:_MAX_PROFILE_EXPERIENCES]]
    return po


def _normalize_contact(raw: dict[str, Any]) -> dict[str, Any]:
    kind = str(raw.get("kind", "other")).strip().lower()
    if kind not in CONTACT_KIND_KEYS:
        kind = "other"
    cid = str(raw.get("id") or "").strip() or str(uuid4())
    return {
        "id": cid,
        "kind": kind,
        "value": str(raw.get("value", "")).strip()[:500],
        "note": str(raw.get("note", "")).strip()[:500] or None,
        "role": str(raw.get("role", "")).strip()[:120] or None,
        "is_primary": bool(raw.get("is_primary")),
    }


class OpportunitiesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, opportunity_id: UUID) -> Opportunity | None:
        q = select(Opportunity).where(Opportunity.id == opportunity_id)
        r = await self.session.execute(q)
        return r.scalar_one_or_none()

    async def get_by_job_and_preview_index(
        self, job_id: UUID, exa_preview_index: int
    ) -> Opportunity | None:
        q = select(Opportunity).where(
            Opportunity.job_id == job_id,
            Opportunity.exa_preview_index == exa_preview_index,
        )
        r = await self.session.execute(q)
        return r.scalar_one_or_none()

    async def list_opportunities(
        self,
        *,
        stage: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Opportunity]:
        q = select(Opportunity).order_by(Opportunity.updated_at.desc())
        if stage and stage in OPPORTUNITY_STAGE_KEYS:
            q = q.where(Opportunity.stage == stage)
        q = q.offset(offset).limit(limit)
        r = await self.session.execute(q)
        return list(r.scalars().all())

    def _set_owner(self, opp: Opportunity, owner_user_id: UUID) -> None:
        opp.owner_user_id = owner_user_id
        opp.updated_at = datetime.now(timezone.utc)

    async def create_or_get_from_preview(
        self, job: SearchJob, exa_preview_index: int, owner_user_id: UUID | None = None
    ) -> tuple[Opportunity, bool]:
        existing = await self.get_by_job_and_preview_index(job.id, exa_preview_index)
        if existing is not None:
            return existing, False

        row = _find_preview_row(job, exa_preview_index)
        if row is None:
            raise ValueError("preview_row_not_found")

        title = str(row.get("title", "")).strip()[:500] or "Sin título"
        url = str(row.get("url", "")).strip()[:2000]
        sn = row.get("snippet")
        snippet = str(sn).strip()[:4000] if sn is not None else None
        spec = str(row.get("specialty", "")).strip()[:160]
        city = str(row.get("city", "")).strip()[:120]

        now = datetime.now(timezone.utc)
        initial_note = {
            "at": now.isoformat(),
            "stage": DEFAULT_OPPORTUNITY_STAGE,
            "author": "sistema",
            "text": "Oportunidad creada desde vista previa Exa.",
        }
        opp = Opportunity(
            job_id=job.id,
            exa_preview_index=exa_preview_index,
            title=title,
            source_url=url,
            snippet=snippet,
            specialty=spec,
            city=city,
            stage=DEFAULT_OPPORTUNITY_STAGE,
            response_outcome=None,
            contacts=[],
            activity_timeline=[initial_note],
            owner_user_id=owner_user_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(opp)
        await self.session.commit()
        await self.session.refresh(opp)
        return opp, True

    async def append_bitacora(
        self,
        opp: Opportunity,
        text: str,
        *,
        author: str = "usuario",
        owner_user_id: UUID | None = None,
    ) -> Opportunity:
        entry = {
            "at": _utc_iso(),
            "stage": opp.stage,
            "author": author.strip()[:64] or "usuario",
            "text": text.strip()[:4000],
        }
        timeline = list(opp.activity_timeline or [])
        timeline.append(entry)
        opp.activity_timeline = timeline
        if owner_user_id is not None:
            self._set_owner(opp, owner_user_id)
        else:
            opp.updated_at = datetime.now(timezone.utc)
        self.session.add(opp)
        await self.session.commit()
        await self.session.refresh(opp)
        return opp

    async def update_stage(
        self,
        opp: Opportunity,
        *,
        stage: str | None = None,
        response_outcome: str | None = None,
        note: str | None = None,
        owner_user_id: UUID | None = None,
        author_for_note: str = "usuario",
    ) -> Opportunity:
        if stage is not None:
            if stage not in OPPORTUNITY_STAGE_KEYS:
                raise ValueError("invalid_stage")
            try:
                current_idx = OPPORTUNITY_STAGE_KEYS.index(str(opp.stage))
            except ValueError:
                current_idx = 0
            new_idx = OPPORTUNITY_STAGE_KEYS.index(stage)
            if new_idx < current_idx:
                raise ValueError("stage_regression")
            opp.stage = stage
        if response_outcome is not None:
            ro = response_outcome.strip().lower()
            if ro not in RESPONSE_OUTCOME_KEYS:
                raise ValueError("invalid_response_outcome")
            opp.response_outcome = ro
        if note and note.strip():
            timeline = list(opp.activity_timeline or [])
            timeline.append(
                {
                    "at": _utc_iso(),
                    "stage": opp.stage,
                    "author": author_for_note.strip()[:64] or "usuario",
                    "text": note.strip()[:4000],
                }
            )
            opp.activity_timeline = timeline
        if owner_user_id is not None:
            self._set_owner(opp, owner_user_id)
        else:
            opp.updated_at = datetime.now(timezone.utc)
        self.session.add(opp)
        await self.session.commit()
        await self.session.refresh(opp)
        return opp

    async def merge_profile_overrides(
        self, opp: Opportunity, updates: dict[str, Any], *, owner_user_id: UUID | None = None
    ) -> Opportunity:
        base = opp.profile_overrides if isinstance(opp.profile_overrides, dict) else {}
        opp.profile_overrides = apply_profile_overrides_patch(base, updates)
        if owner_user_id is not None:
            self._set_owner(opp, owner_user_id)
        else:
            opp.updated_at = datetime.now(timezone.utc)
        self.session.add(opp)
        await self.session.commit()
        await self.session.refresh(opp)
        return opp

    async def replace_contacts(
        self, opp: Opportunity, contacts: list[dict[str, Any]], *, owner_user_id: UUID | None = None
    ) -> Opportunity:
        normalized: list[dict[str, Any]] = []
        primary_seen = False
        for c in contacts:
            if not isinstance(c, dict):
                continue
            n = _normalize_contact(c)
            if n["is_primary"]:
                if primary_seen:
                    n["is_primary"] = False
                else:
                    primary_seen = True
            normalized.append(n)
        opp.contacts = normalized
        if owner_user_id is not None:
            self._set_owner(opp, owner_user_id)
        else:
            opp.updated_at = datetime.now(timezone.utc)
        self.session.add(opp)
        await self.session.commit()
        await self.session.refresh(opp)
        return opp
