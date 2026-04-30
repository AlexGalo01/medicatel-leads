from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.api.deps import get_current_user, require_admin, require_permission
from mle.api.schemas import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    AdminUsersListResponse,
    OpportunityCreateManualRequest,
    DirectoryEntriesListResponse,
    DirectoryEntryItemResponse,
    ExaMoreResultsRequest,
    ExaMoreResultsResponse,
    LeadCrmUpdateRequest,
    LeadDetailResponse,
    LeadItemResponse,
    LeadsExportRequest,
    LeadsExportResponse,
    LeadsListResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    OpportunityBitacoraRequest,
    OpportunityContactsReplaceRequest,
    OpportunityCreateFromPreviewRequest,
    OpportunityEnrichResponse,
    OpportunityListItemResponse,
    OpportunityListResponse,
    OpportunityOwnerSnippet,
    OpportunityResponse,
    OpportunityUpdateRequest,
    ProfileInterpretItemResponse,
    ProfileInterpretRequest,
    ProfileInterpretResponse,
    ProfileSummaryRequest,
    ProfileSummaryExperienceItem,
    ProfileSummaryResponse,
    ClarifySearchJobRequest,
    ClarifySearchJobResponse,
    SearchJobCreateRequest,
    SearchJobCreateResponse,
    SearchJobListItemResponse,
    SearchJobsListResponse,
    SearchJobStatusResponse,
    UserPublic,
)
from mle.db.base import async_session_factory
from mle.db.models import Opportunity, User
from mle.repositories.directories_repository import DirectoriesRepository
from mle.repositories.directory_entries_repository import DirectoryEntriesRepository
from mle.repositories.jobs_repository import JobsRepository
from mle.repositories.leads_repository import LeadsRepository
from mle.repositories.opportunities_repository import OpportunitiesRepository
from mle.repositories.users_repository import UsersRepository
from mle.schemas.directories import (
    DirectoryCreateRequest,
    DirectoryListResponse,
    DirectoryRead,
    DirectoryStepCreate,
    DirectoryStepRead,
    DirectoryStepReorder,
    DirectoryStepUpdate,
    DirectoryUpdateRequest,
    OpportunityMoveStepRequest,
    OpportunityReopenRequest,
    OpportunityTerminateRequest,
    StepDeleteRequest,
)
from mle.services.jwt_service import create_access_token
from mle.services.passwords import hash_password, verify_password
from mle.services.export_service import export_leads_to_csv
from mle.services.pipeline_service import run_job_pipeline
from mle.services.query_expansion_service import expand_user_search_query
from mle.services.exa_more_results_service import append_exa_results_for_job
from mle.services.profile_interpret_service import interpret_profile_texts
from mle.services.profile_interpret_service import extract_profile_summary
from mle.services.lead_deep_enrich_service import LeadCore, enrich_lead_contacts, EnrichmentResult
from mle.clients.exa_client import ExaClient
from mle.clients.opencli_client import OpenCliClient
from mle.clients.llm_factory import get_llm_client, get_reviewer_llm_client
from mle.core.config import get_settings, effective_exa_search_timeout_seconds
from mle.schemas.leads import LeadRead
from mle.schemas.opportunities import OPPORTUNITY_STAGE_KEYS

logger = logging.getLogger(__name__)

public_router = APIRouter(tags=["auth"])
protected_router = APIRouter(tags=["mle"], dependencies=[Depends(get_current_user)])


def _raise_not_found(entity_name: str) -> None:
    raise HTTPException(status_code=404, detail=f"{entity_name} no encontrado")


def _pipeline_error_message(metadata: Any, *, max_length: int = 800) -> str | None:
    """Último error del pipeline (lista `pipeline_errors` en metadata del job)."""
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("pipeline_errors")
    if not isinstance(raw, list) or not raw:
        return None
    parts = [str(x).strip() for x in raw if str(x).strip()]
    if not parts:
        return None
    text = parts[-1]
    if len(text) > max_length:
        return f"{text[: max_length - 1]}…"
    return text


def _owner_to_snippet(u: User | None) -> OpportunityOwnerSnippet | None:
    if u is None:
        return None
    return OpportunityOwnerSnippet(
        user_id=str(u.id),
        display_name=u.display_name,
        email=u.email,
    )


def _opportunity_to_response(
    opp: Opportunity, *, owner: User | None = None, created: bool = False
) -> OpportunityResponse:
    po = opp.profile_overrides if isinstance(opp.profile_overrides, dict) else {}
    return OpportunityResponse(
        opportunity_id=str(opp.id),
        job_id=str(opp.job_id) if opp.job_id else None,
        exa_preview_index=opp.exa_preview_index,
        directory_id=str(opp.directory_id) if opp.directory_id else None,
        current_step_id=str(opp.current_step_id) if opp.current_step_id else None,
        title=opp.title,
        source_url=opp.source_url,
        snippet=opp.snippet,
        specialty=opp.specialty,
        city=opp.city,
        stage=opp.stage,
        response_outcome=opp.response_outcome,
        terminated_at=opp.terminated_at,
        terminated_outcome=opp.terminated_outcome,
        terminated_note=opp.terminated_note,
        contacts=list(opp.contacts or []),
        activity_timeline=list(opp.activity_timeline or []),
        profile_overrides=dict(po),
        contact_type=opp.contact_type,
        created_at=opp.created_at,
        updated_at=opp.updated_at,
        created=created,
        owner=_owner_to_snippet(owner),
    )


async def _load_owner_user(session: AsyncSession, opp: Opportunity) -> User | None:
    if not opp.owner_user_id:
        return None
    return await session.get(User, opp.owner_user_id)


async def _load_owners_map(session: AsyncSession, opps: list[Opportunity]) -> dict[UUID, User]:
    ids = {o.owner_user_id for o in opps if o.owner_user_id}
    if not ids:
        return {}
    r = await session.execute(select(User).where(User.id.in_(list(ids))))
    return {u.id: u for u in r.scalars().all()}


def _lead_read_to_detail(lead: LeadRead) -> LeadDetailResponse:
    crm_payload = lead.langsmith_metadata.get("crm", {}) if isinstance(lead.langsmith_metadata, dict) else {}
    activity_timeline = crm_payload.get("activity_timeline", [])
    if not isinstance(activity_timeline, list):
        activity_timeline = []
    deep = lead.langsmith_metadata.get("last_deep_enrich", {}) if isinstance(lead.langsmith_metadata, dict) else {}
    deep_status = str(deep.get("status")) if isinstance(deep, dict) and deep.get("status") else None
    deep_message = str(deep.get("message")) if isinstance(deep, dict) and deep.get("message") else None

    return LeadDetailResponse(
        lead_id=str(lead.id),
        full_name=lead.full_name,
        specialty=lead.specialty,
        city=lead.city,
        country=lead.country,
        score=lead.score,
        score_reasoning=lead.score_reasoning,
        email=lead.contacts.email,
        whatsapp=lead.contacts.whatsapp,
        linkedin_url=str(lead.contacts.linkedin_url) if lead.contacts.linkedin_url else None,
        primary_source_url=str(lead.primary_source_url) if lead.primary_source_url else None,
        validation_status=lead.validation_status,
        source_citations=_serialize_source_citations(lead.source_citations),
        crm_stage=str(crm_payload.get("stage", "new")),
        crm_notes=str(crm_payload.get("notes", "")).strip() or None,
        activity_timeline=[item for item in activity_timeline if isinstance(item, dict)],
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        enrichment_status=deep_status,
        enrichment_message=deep_message,
    )


def _serialize_source_citations(raw_citations: list[object]) -> list[dict[str, object]]:
    serialized_items: list[dict[str, object]] = []
    for citation_item in raw_citations:
        if isinstance(citation_item, dict):
            serialized_items.append(citation_item)
            continue
        model_dump_fn = getattr(citation_item, "model_dump", None)
        if callable(model_dump_fn):
            dumped_value = model_dump_fn()
            if isinstance(dumped_value, dict):
                serialized_items.append(dumped_value)
    return serialized_items


@protected_router.post("/search-jobs", response_model=SearchJobCreateResponse, status_code=202)
async def create_search_job(
    payload: SearchJobCreateRequest,
    _u: User = Depends(require_permission("use_search")),
) -> SearchJobCreateResponse:
    contact_channels = payload.contact_channels or ["email", "whatsapp", "linkedin"]
    user_query = payload.query.strip()
    combined_parts: list[str] = []
    if payload.notes and payload.notes.strip():
        combined_parts.append(payload.notes.strip())
    if payload.exa_criteria and payload.exa_criteria.strip():
        combined_parts.append("Criterios específicos para Exa:\n" + payload.exa_criteria.strip())
    combined_notes = "\n\n".join(combined_parts) if combined_parts else None

    expanded_query, expansion_meta, search_plan = await expand_user_search_query(
        user_query=user_query,
        contact_channels=contact_channels,
        search_focus=payload.search_focus,
        notes=combined_notes,
    )
    plan_dict: dict[str, object] = dict(search_plan) if isinstance(search_plan, dict) else {}
    if payload.exa_category in ("people", "company"):
        plan_dict["exa_category"] = payload.exa_category

    job_metadata: dict[str, object] = {
        "query_text": expanded_query,
        "user_query": user_query,
        "query_expansion_metadata": expansion_meta,
        "search_plan": plan_dict,
    }
    if payload.exa_criteria and payload.exa_criteria.strip():
        job_metadata["exa_criteria"] = payload.exa_criteria.strip()
    if payload.exa_category in ("people", "company"):
        job_metadata["exa_category_client"] = payload.exa_category

    cq_raw = plan_dict.get("clarifying_question")
    if (cq_raw is None or (isinstance(cq_raw, str) and not cq_raw.strip())) and isinstance(
        expansion_meta, dict
    ):
        cq_raw = expansion_meta.get("clarifying_question")
    cq = cq_raw.strip() if isinstance(cq_raw, str) else None
    if cq == "":
        cq = None
    requires_clarification = bool(cq)
    job_metadata["awaiting_clarification"] = requires_clarification
    if isinstance(job_metadata.get("search_plan"), dict) and cq:
        sp = dict(job_metadata["search_plan"])
        sp["clarifying_question"] = cq
        job_metadata["search_plan"] = sp

    async with async_session_factory() as session:
        dirs_repo = DirectoriesRepository(session)
        directory = await dirs_repo.get(payload.directory_id)
        if directory is None:
            raise HTTPException(status_code=404, detail="Directorio destino no encontrado.")
        jobs_repository = JobsRepository(session)
        created_job = await jobs_repository.create(
            expanded_query_text=expanded_query,
            requested_contact_channels=contact_channels,
            notes=payload.notes.strip() if payload.notes and payload.notes.strip() else None,
            metadata_json=job_metadata,
            directory_id=payload.directory_id,
        )

    if not requires_clarification:
        asyncio.create_task(run_job_pipeline(created_job.id))
    else:
        logger.info(
            "Job creado en espera de aclaracion job_id=%s (pipeline no iniciado hasta POST /clarify)",
            created_job.id,
        )
    return SearchJobCreateResponse(
        job_id=str(created_job.id),
        status=created_job.status,
        created_at=created_job.created_at,
        clarifying_question=cq,
        requires_clarification=requires_clarification,
    )


@protected_router.post(
    "/search-jobs/{job_id}/clarify",
    response_model=ClarifySearchJobResponse,
    status_code=200,
)
async def clarify_search_job(
    job_id: UUID,
    payload: ClarifySearchJobRequest,
    _u: User = Depends(require_permission("use_search")),
) -> ClarifySearchJobResponse:
    """Re-expande la consulta con la aclaración del usuario y arranca el pipeline."""
    reply = payload.reply.strip()
    async with async_session_factory() as session:
        jobs_repository = JobsRepository(session)
        job = await jobs_repository.get_by_id(job_id)
        if job is None:
            _raise_not_found("Job")
        meta = dict(job.metadata_json) if isinstance(job.metadata_json, dict) else {}
        if job.status != "pending":
            raise HTTPException(
                status_code=409,
                detail="Este trabajo ya no admite aclaraciones.",
            )
        if not meta.get("awaiting_clarification"):
            raise HTTPException(
                status_code=409,
                detail="Este trabajo no está esperando una aclaración.",
            )

        user_query = str(meta.get("user_query") or "").strip()
        if not user_query:
            raise HTTPException(status_code=400, detail="Falta la consulta original del trabajo.")

        contact_channels = list(job.requested_contact_channels or ["email", "whatsapp", "linkedin"])
        search_focus: str | None = None
        qem = meta.get("query_expansion_metadata")
        if isinstance(qem, dict) and qem.get("focus"):
            search_focus = str(qem["focus"])

        combined_parts: list[str] = []
        if job.notes and job.notes.strip():
            combined_parts.append(job.notes.strip())
        exa_crit = meta.get("exa_criteria")
        if isinstance(exa_crit, str) and exa_crit.strip():
            combined_parts.append("Criterios específicos para Exa:\n" + exa_crit.strip())
        combined_parts.append(f"Aclaración del usuario:\n{reply}")
        combined_notes = "\n\n".join(combined_parts)

        expanded_query, expansion_meta, search_plan = await expand_user_search_query(
            user_query=user_query,
            contact_channels=contact_channels,
            search_focus=search_focus,
            notes=combined_notes,
        )
        plan_dict: dict[str, object] = dict(search_plan) if isinstance(search_plan, dict) else {}
        exa_cat_client = meta.get("exa_category_client")
        if exa_cat_client in ("people", "company"):
            plan_dict["exa_category"] = exa_cat_client

        new_meta: dict[str, object] = {
            **meta,
            "query_text": expanded_query,
            "query_expansion_metadata": expansion_meta,
            "search_plan": plan_dict,
            "awaiting_clarification": False,
            "user_clarification_reply": reply,
        }
        if isinstance(exa_crit, str) and exa_crit.strip():
            new_meta["exa_criteria"] = exa_crit.strip()

        updated = await jobs_repository.update_pending_job_after_clarify(
            job_id,
            expanded_query_text=expanded_query,
            metadata_json=new_meta,
            notes=job.notes,
        )
        if updated is None:
            raise HTTPException(status_code=500, detail="No se pudo actualizar el trabajo.")

    asyncio.create_task(run_job_pipeline(job_id))
    return ClarifySearchJobResponse(job_id=str(job_id), status=updated.status)


@protected_router.get("/search-jobs", response_model=SearchJobsListResponse)
async def list_search_jobs(
    limit: int | None = Query(default=15, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    directory_id: UUID | None = Query(default=None),
    _u: User = Depends(require_permission("use_search")),
) -> SearchJobsListResponse:
    async with async_session_factory() as session:
        jobs_repository = JobsRepository(session)
        jobs, total = await jobs_repository.list_jobs(
            limit=limit, offset=offset, query_text=q, directory_id=directory_id
        )
        # Mapear directorios referenciados por los jobs para devolver nombre.
        dir_ids = {job.directory_id for job in jobs if job.directory_id is not None}
        dir_name_map: dict[UUID, str] = {}
        if dir_ids:
            from mle.db.models import Directory
            result = await session.execute(
                select(Directory).where(Directory.id.in_(list(dir_ids)))
            )
            for d in result.scalars().all():
                dir_name_map[d.id] = d.name

    items: list[SearchJobListItemResponse] = []
    for job in jobs:
        meta = job.metadata_json if isinstance(job.metadata_json, dict) else {}
        query_text = str(meta.get("user_query") or meta.get("query_text") or job.specialty or "").strip()
        plan = meta.get("search_plan")
        exa_category: str | None = None
        if isinstance(plan, dict):
            raw_cat = plan.get("exa_category")
            if raw_cat in ("people", "company"):
                exa_category = str(raw_cat)
        if exa_category is None:
            cat_client = meta.get("exa_category_client")
            if cat_client in ("people", "company"):
                exa_category = str(cat_client)
        err_hint = (
            _pipeline_error_message(meta, max_length=160)
            if job.status == "error"
            else None
        )
        items.append(
            SearchJobListItemResponse(
                job_id=str(job.id),
                query=query_text or f"Búsqueda {str(job.id)[:8]}",
                status=job.status,
                created_at=job.created_at,
                exa_category=exa_category,
                directory_id=str(job.directory_id) if job.directory_id else None,
                directory_name=dir_name_map.get(job.directory_id) if job.directory_id else None,
                error_message=err_hint,
            )
        )
    page_size = limit if limit is not None else max(total, 1)
    page = (offset // page_size) + 1 if page_size > 0 else 1
    total_pages = max(1, (total + page_size - 1) // page_size) if page_size > 0 else 1
    return SearchJobsListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@protected_router.get("/search-jobs/{job_id}", response_model=SearchJobStatusResponse)
async def get_search_job_status(
    job_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> SearchJobStatusResponse:
    async with async_session_factory() as session:
        jobs_repository = JobsRepository(session)
        job = await jobs_repository.get_by_id(job_id)
        if job is None:
            _raise_not_found("Job")

    pipeline_stage = str(job.metadata_json.get("pipeline_stage", job.status))
    metrics = {
        "sources_visited": int(job.metadata_json.get("sources_visited", 0)),
        "leads_extracted": int(job.metadata_json.get("leads_extracted", 0)),
        "leads_scored": int(job.metadata_json.get("stored_leads", 0)),
    }
    quality_metrics = {
        "contact_coverage": float(job.metadata_json.get("contact_coverage", 0.0)),
        "missing_contact_count": int(job.metadata_json.get("missing_contact_count", 0)),
        "retry_used": bool(job.metadata_json.get("retry_used", False)),
        "discarded_leads_count": int(job.metadata_json.get("discarded_leads_count", 0)),
    }
    preview_raw = job.metadata_json.get("exa_results_preview")
    exa_preview: list[dict[str, Any]] = preview_raw if isinstance(preview_raw, list) else []
    pipeline_mode_value = job.metadata_json.get("pipeline_mode")
    pipeline_mode = str(pipeline_mode_value) if pipeline_mode_value else None

    sp = job.metadata_json.get("search_plan")
    exa_cat: str | None = None
    if isinstance(sp, dict):
        raw_cat = sp.get("exa_category")
        if raw_cat in ("people", "company"):
            exa_cat = str(raw_cat)
    exa_crit_raw = job.metadata_json.get("exa_criteria")
    exa_crit = str(exa_crit_raw).strip() if exa_crit_raw else None
    query_text = str(job.metadata_json.get("user_query") or job.metadata_json.get("query_text") or job.specialty or "").strip() or None
    err_detail = (
        _pipeline_error_message(job.metadata_json, max_length=1200)
        if job.status == "error"
        else None
    )

    meta_job = job.metadata_json if isinstance(job.metadata_json, dict) else {}
    awaiting_clarification = bool(meta_job.get("awaiting_clarification")) and job.status == "pending"
    clarifying_display: str | None = None
    if awaiting_clarification and isinstance(sp, dict):
        raw_cq_status = sp.get("clarifying_question")
        if isinstance(raw_cq_status, str) and raw_cq_status.strip():
            clarifying_display = raw_cq_status.strip()

    return SearchJobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress,
        current_stage=pipeline_stage,
        metrics=metrics,
        quality_metrics=quality_metrics,
        updated_at=job.updated_at,
        pipeline_mode=pipeline_mode,
        exa_results_preview=exa_preview,
        notes=job.notes,
        exa_category=exa_cat,
        exa_criteria=exa_crit,
        query_text=query_text,
        error_message=err_detail,
        awaiting_clarification=awaiting_clarification,
        clarifying_question=clarifying_display,
    )


@protected_router.post("/profiles/interpret", response_model=ProfileInterpretResponse)
async def interpret_profiles(
    payload: ProfileInterpretRequest,
    _u: User = Depends(require_permission("use_search")),
) -> ProfileInterpretResponse:
    normalized_texts = [text.strip() for text in payload.texts if text.strip()]
    interpreted_items = await interpret_profile_texts(normalized_texts)
    items = [
        ProfileInterpretItemResponse(
            source_text=source_text,
            normalized_name=interpreted.get("normalized_name"),
            normalized_company=interpreted.get("normalized_company"),
            normalized_specialty=interpreted.get("normalized_specialty"),
        )
        for source_text, interpreted in zip(normalized_texts, interpreted_items, strict=False)
    ]
    return ProfileInterpretResponse(items=items)


@protected_router.post("/profiles/summary", response_model=ProfileSummaryResponse)
async def summarize_profile(
    payload: ProfileSummaryRequest,
    _u: User = Depends(require_permission("use_search")),
) -> ProfileSummaryResponse:
    summary = await extract_profile_summary(
        title=payload.title,
        specialty=payload.specialty,
        city=payload.city,
        snippet=payload.snippet,
    )
    confidence = str(summary.get("confidence") or "low").lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "low"
    normalized_confidence: str = confidence
    return ProfileSummaryResponse(
        professional_summary=summary.get("professional_summary"),
        company=summary.get("company"),
        location=summary.get("location"),
        about=summary.get("about"),
        experiences=[
            ProfileSummaryExperienceItem(
                role=str(item.get("role") or "").strip(),
                organization=str(item.get("organization")).strip() if item.get("organization") else None,
                period=str(item.get("period")).strip() if item.get("period") else None,
            )
            for item in (summary.get("experiences") or [])
            if isinstance(item, dict) and str(item.get("role") or "").strip()
        ],
        confidence=normalized_confidence,  # pydantic valida el literal
        notes=summary.get("notes"),
    )


@protected_router.post(
    "/search-jobs/{job_id}/exa-more",
    response_model=ExaMoreResultsResponse,
)
async def load_more_exa_results(
    job_id: UUID,
    payload: ExaMoreResultsRequest,
    _u: User = Depends(require_permission("use_search")),
) -> ExaMoreResultsResponse:
    result = await append_exa_results_for_job(job_id, payload.num_results)
    if not result.get("ok"):
        err = str(result.get("error") or "Error desconocido")
        if err == "Job no encontrado":
            _raise_not_found("Job")
        return ExaMoreResultsResponse(ok=False, error=err)
    return ExaMoreResultsResponse(
        ok=True,
        added_count=int(result.get("added_count", 0)),
        total_count=int(result.get("total_count", 0)),
        preview_count=int(result.get("preview_count", 0)),
        query_used=result.get("query_used"),
    )


@protected_router.get("/search-jobs/{job_id}/directory-entries", response_model=DirectoryEntriesListResponse)
async def list_job_directory_entries(
    job_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _u: User = Depends(require_permission("use_search")),
) -> DirectoryEntriesListResponse:
    async with async_session_factory() as session:
        jobs_repository = JobsRepository(session)
        job = await jobs_repository.get_by_id(job_id)
        if job is None:
            _raise_not_found("Job")
        directory_repo = DirectoryEntriesRepository(session)
        rows, total = await directory_repo.list_by_job(job_id, page=page, page_size=page_size)

    items = [
        DirectoryEntryItemResponse(
            entry_id=str(row.id),
            display_title=row.display_title,
            primary_url=row.primary_url,
            snippet=row.snippet,
            entity_type=row.entity_type,
            city=row.city,
            country=row.country,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return DirectoryEntriesListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


@protected_router.get("/leads", response_model=LeadsListResponse)
async def list_leads(
    job_id: UUID = Query(...),
    min_score: float | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    contact_filter: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _u: User = Depends(require_permission("use_search")),
) -> LeadsListResponse:
    async with async_session_factory() as session:
        leads_repository = LeadsRepository(session)
        leads_page = await leads_repository.list_by_job(
            job_id=job_id,
            min_score=min_score,
            name_query=q,
            contact_filter=contact_filter,
            page=page,
            page_size=page_size,
        )

    items = [
        LeadItemResponse(
            lead_id=str(lead.id),
            full_name=lead.full_name,
            specialty=lead.specialty,
            city=lead.city,
            score=lead.score,
            email=lead.contacts.email,
            whatsapp=lead.contacts.whatsapp,
            linkedin_url=str(lead.contacts.linkedin_url) if lead.contacts.linkedin_url else None,
            primary_source_url=str(lead.primary_source_url) if lead.primary_source_url else None,
        )
        for lead in leads_page.items
    ]
    return LeadsListResponse(
        items=items,
        page=leads_page.page,
        page_size=leads_page.page_size,
        total=leads_page.total,
    )


@protected_router.get("/leads/{lead_id}", response_model=LeadDetailResponse)
async def get_lead_detail(
    lead_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> LeadDetailResponse:
    async with async_session_factory() as session:
        leads_repository = LeadsRepository(session)
        lead = await leads_repository.get_by_id(lead_id)
        if lead is None:
            _raise_not_found("Lead")

    return _lead_read_to_detail(lead)


@protected_router.patch("/leads/{lead_id}/crm", response_model=LeadDetailResponse)
async def update_lead_crm(
    lead_id: UUID,
    payload: LeadCrmUpdateRequest,
    _u: User = Depends(require_permission("use_search")),
) -> LeadDetailResponse:
    activity_entry: dict[str, str] | None = None
    normalized_activity_note = payload.activity_note.strip() if payload.activity_note else ""
    if normalized_activity_note:
        activity_entry = {
            "note": normalized_activity_note,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    async with async_session_factory() as session:
        leads_repository = LeadsRepository(session)
        updated_lead = await leads_repository.update_crm_data(
            lead_id=lead_id,
            crm_stage=payload.crm_stage.strip() if payload.crm_stage else None,
            crm_notes=payload.crm_notes.strip() if payload.crm_notes else None,
            activity_entry=activity_entry,
        )
        if updated_lead is None:
            _raise_not_found("Lead")

        return _lead_read_to_detail(updated_lead)


@protected_router.post("/leads/export", response_model=LeadsExportResponse)
async def export_leads(
    payload: LeadsExportRequest,
    _u: User = Depends(require_permission("use_search")),
) -> LeadsExportResponse:
    if payload.format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Formato no soportado, usa csv")

    try:
        job_id = UUID(payload.job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="job_id invalido") from exc

    min_score = payload.filters.get("min_score")
    parsed_min_score = float(min_score) if min_score is not None else None
    name_q = payload.filters.get("q")
    contact_f = payload.filters.get("contact_filter")
    name_query = str(name_q).strip() if name_q else None
    contact_filter = str(contact_f).strip() if contact_f else None

    async with async_session_factory() as session:
        leads_repository = LeadsRepository(session)
        leads_page = await leads_repository.list_by_job(
            job_id=job_id,
            min_score=parsed_min_score,
            name_query=name_query,
            contact_filter=contact_filter,
            page=1,
            page_size=5000,
        )

    leads_payload = [
        {
            "full_name": lead.full_name,
            "specialty": lead.specialty,
            "country": lead.country,
            "city": lead.city,
            "score": lead.score,
            "score_reasoning": lead.score_reasoning,
            "email": lead.contacts.email,
            "whatsapp": lead.contacts.whatsapp,
            "linkedin_url": str(lead.contacts.linkedin_url) if lead.contacts.linkedin_url else None,
        }
        for lead in leads_page.items
    ]
    settings = get_settings()
    export_path = export_leads_to_csv(
        job_id=job_id,
        leads=leads_payload,
        export_dir_path=settings.export_dir,
    )
    return LeadsExportResponse(
        download_path=export_path,
        generated_at=datetime.now(timezone.utc),
    )


@protected_router.get("/leads/export/file")
async def export_leads_file(
    job_id: UUID = Query(...),
    min_score: float | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    contact_filter: str | None = Query(default=None, max_length=40),
    _u: User = Depends(require_permission("use_search")),
) -> FileResponse:
    async with async_session_factory() as session:
        leads_repository = LeadsRepository(session)
        leads_page = await leads_repository.list_by_job(
            job_id=job_id,
            min_score=min_score,
            name_query=q,
            contact_filter=contact_filter,
            page=1,
            page_size=5000,
        )

    leads_payload = [
        {
            "full_name": lead.full_name,
            "specialty": lead.specialty,
            "country": lead.country,
            "city": lead.city,
            "score": lead.score,
            "score_reasoning": lead.score_reasoning,
            "email": lead.contacts.email,
            "whatsapp": lead.contacts.whatsapp,
            "linkedin_url": str(lead.contacts.linkedin_url) if lead.contacts.linkedin_url else None,
        }
        for lead in leads_page.items
    ]
    settings = get_settings()
    export_path_str = export_leads_to_csv(
        job_id=job_id,
        leads=leads_payload,
        export_dir_path=settings.export_dir,
    )
    export_path = Path(export_path_str)
    if not export_path.is_file():
        raise HTTPException(status_code=500, detail="No se pudo generar el archivo CSV")

    return FileResponse(
        path=str(export_path),
        filename=f"leads_{job_id}.csv",
        media_type="text/csv; charset=utf-8",
    )


@protected_router.get(
    "/opportunities/by-preview",
    response_model=OpportunityResponse,
    responses={404: {"description": "No existe oportunidad para ese preview"}},
)
async def get_opportunity_by_preview(
    job_id: UUID = Query(...),
    exa_preview_index: int = Query(..., ge=1),
) -> OpportunityResponse:
    async with async_session_factory() as session:
        repo = OpportunitiesRepository(session)
        opp = await repo.get_by_job_and_preview_index(job_id, exa_preview_index)
        if opp is None:
            _raise_not_found("Oportunidad")
        owner = await _load_owner_user(session, opp)
        return _opportunity_to_response(opp, owner=owner, created=False)


@protected_router.post("/opportunities/from-preview", response_model=OpportunityResponse)
async def create_opportunity_from_preview(
    payload: OpportunityCreateFromPreviewRequest,
    response: Response,
    current: User = Depends(require_permission("manage_opportunities")),
) -> OpportunityResponse:
    async with async_session_factory() as session:
        jobs_repo = JobsRepository(session)
        job = await jobs_repo.get_by_id(payload.job_id)
        if job is None:
            _raise_not_found("Job")
        repo = OpportunitiesRepository(session)
        try:
            opp, created = await repo.create_or_get_from_preview(
                job, payload.exa_preview_index, owner_user_id=current.id
            )
        except ValueError as exc:
            if str(exc) == "preview_row_not_found":
                raise HTTPException(
                    status_code=400,
                    detail="No hay fila de vista previa Exa con ese índice para este job.",
                ) from exc
            raise HTTPException(status_code=400, detail="Datos de oportunidad no válidos.") from exc
        await session.refresh(opp)
        owner = await _load_owner_user(session, opp)
    response.status_code = 201 if created else 200
    return _opportunity_to_response(opp, owner=owner, created=created)


@protected_router.post("/opportunities/manual", response_model=OpportunityResponse, status_code=201)
async def create_opportunity_manual(
    payload: OpportunityCreateManualRequest,
    current: User = Depends(require_permission("manage_opportunities")),
) -> OpportunityResponse:
    async with async_session_factory() as session:
        repo = OpportunitiesRepository(session)
        opp = await repo.create_manual(
            title=payload.title,
            specialty=payload.specialty,
            city=payload.city,
            source_url=payload.source_url,
            snippet=payload.snippet,
            owner_user_id=current.id,
        )
        owner = await _load_owner_user(session, opp)
    return _opportunity_to_response(opp, owner=owner, created=True)


@protected_router.get("/opportunities", response_model=OpportunityListResponse)
async def list_opportunities(
    stage: str | None = Query(default=None, max_length=64),
    job_id: UUID | None = Query(default=None),
    directory_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> OpportunityListResponse:
    if stage is not None and stage != "" and stage not in OPPORTUNITY_STAGE_KEYS:
        raise HTTPException(status_code=400, detail="Fase no válida.")
    async with async_session_factory() as session:
        repo = OpportunitiesRepository(session)
        rows = await repo.list_opportunities(
            stage=stage or None,
            job_id=job_id,
            directory_id=directory_id,
            limit=limit,
            offset=0,
        )
        owners = await _load_owners_map(session, rows)
    items = [
        OpportunityListItemResponse(
            opportunity_id=str(o.id),
            job_id=str(o.job_id) if o.job_id else None,
            exa_preview_index=o.exa_preview_index,
            directory_id=str(o.directory_id) if o.directory_id else None,
            current_step_id=str(o.current_step_id) if o.current_step_id else None,
            title=o.title,
            city=o.city,
            stage=o.stage,
            response_outcome=o.response_outcome,
            terminated_at=o.terminated_at,
            terminated_outcome=o.terminated_outcome,
            updated_at=o.updated_at,
            owner=_owner_to_snippet(owners.get(o.owner_user_id) if o.owner_user_id else None),
        )
        for o in rows
    ]
    return OpportunityListResponse(items=items)


@protected_router.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(opportunity_id: UUID) -> OpportunityResponse:
    async with async_session_factory() as session:
        repo = OpportunitiesRepository(session)
        opp = await repo.get_by_id(opportunity_id)
        if opp is None:
            _raise_not_found("Oportunidad")
        owner = await _load_owner_user(session, opp)
        return _opportunity_to_response(opp, owner=owner, created=False)


@protected_router.post("/opportunities/{opportunity_id}/enrich")
async def enrich_opportunity(opportunity_id: UUID):
    """Enriquece un opportunity buscando contactos (email, teléfono, etc.) en la web.

    Devuelve Server-Sent Events (SSE) con progreso en tiempo real.
    Último evento contiene los datos de enriquecimiento completos.
    """
    async with async_session_factory() as session:
        opp_repo = OpportunitiesRepository(session)
        opp = await opp_repo.get_by_id(opportunity_id)
        if opp is None:
            _raise_not_found("Oportunidad")

        country = ""
        if opp.job_id:
            jobs_repo = JobsRepository(session)
            job = await jobs_repo.get_by_id(opp.job_id)
            if job is not None:
                country = getattr(job, "country", "") or ""

    lead = LeadCore(
        full_name=opp.title or "",
        specialty=opp.specialty or "",
        city=opp.city or "",
        country=country,
        primary_source_url=opp.source_url or "",
    )

    st = get_settings()
    exa_client = ExaClient(
        api_key=st.exa_api_key,
        timeout_seconds=effective_exa_search_timeout_seconds(st),
    )
    opencli = OpenCliClient(st)
    proposer = get_llm_client(st)
    reviewer = get_reviewer_llm_client(st)

    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def send_progress(msg: str):
        """Coroutine que pone progreso en la queue (no async generator)."""
        await queue.put({"stage": msg})

    async def _run_enrichment():
        """Ejecuta enriquecimiento y pone resultado en queue."""
        try:
            result = await enrich_lead_contacts(
                lead,
                exa_client=exa_client,
                opencli=opencli,
                proposer=proposer,
                reviewer=reviewer,
                settings=st,
                exclude_linkedin=True,
                progress_callback=send_progress,
            )
            await queue.put({"__result__": result})
        except Exception as e:
            await queue.put({"__error__": str(e)})

    async def _persist_enrichment(enrichment_result: EnrichmentResult) -> None:
        """Persiste los contactos y metadatos del enriquecimiento en la oportunidad."""
        async with async_session_factory() as session:
            opp_repo = OpportunitiesRepository(session)
            current_opp = await opp_repo.get_by_id(opportunity_id)
            if current_opp is None:
                return

            # Construir lista de contactos nuevos sin sobrescribir existentes del mismo kind
            existing_contacts = [c for c in (current_opp.contacts or []) if isinstance(c, dict)]
            existing_kinds = {str(c.get("kind", "")).lower() for c in existing_contacts}
            new_contacts = list(existing_contacts)

            for kind, value in [
                ("email", enrichment_result.email),
                ("phone", enrichment_result.phone),
                ("whatsapp", enrichment_result.whatsapp),
                ("website", enrichment_result.website),
                ("linkedin", enrichment_result.linkedin_url),
                ("facebook_url", enrichment_result.facebook_url),
                ("instagram_url", enrichment_result.instagram_url),
            ]:
                if value and kind.lower() not in existing_kinds:
                    new_contacts.append({
                        "id": f"enrich-{kind}-{uuid4()}",
                        "kind": kind,
                        "value": str(value)[:500],
                        "note": enrichment_result.contact_sources.get(kind),
                        "role": None,
                        "is_primary": len(new_contacts) == 0,
                    })

            # Guardar contactos
            if new_contacts != existing_contacts:
                await opp_repo.replace_contacts(current_opp, new_contacts)

            # Guardar metadatos de enriquecimiento
            overrides = {
                "enrichment_status": enrichment_result.status,
                "enrichment_message": enrichment_result.message,
            }
            if enrichment_result.address:
                overrides["address"] = enrichment_result.address
            if enrichment_result.schedule_text:
                overrides["schedule_text"] = enrichment_result.schedule_text
            if enrichment_result.description:
                overrides["description"] = enrichment_result.description
            await opp_repo.merge_profile_overrides(current_opp, overrides)

    async def generate():
        """Genera SSE events desde la queue."""
        task = asyncio.create_task(_run_enrichment())
        try:
            while True:
                item = await asyncio.wait_for(queue.get(), timeout=180)

                if "__result__" in item:
                    result: EnrichmentResult = item["__result__"]

                    # Persistir enriquecimiento
                    await _persist_enrichment(result)

                    response_data = OpportunityEnrichResponse(
                        status=result.status,
                        message=result.message,
                        email=result.email,
                        phone=result.phone,
                        whatsapp=result.whatsapp,
                        address=result.address,
                        schedule_text=result.schedule_text,
                        website=result.website,
                        facebook_url=result.facebook_url,
                        instagram_url=result.instagram_url,
                        linkedin_url=result.linkedin_url,
                        description=result.description,
                        citations=result.citations,
                    )
                    yield f"event: done\ndata: {response_data.model_dump_json()}\n\n"
                    break

                elif "__error__" in item:
                    error_data = {"error": str(item["__error__"])}
                    yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                    break

                else:
                    # Progress event
                    yield f"data: {json.dumps(item)}\n\n"

        except asyncio.TimeoutError:
            task.cancel()
            error_data = {"error": "Timeout durante enriquecimiento"}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
        except Exception as e:
            task.cancel()
            error_data = {"error": str(e)}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(generate(), media_type="text/event-stream")


@protected_router.patch("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
async def patch_opportunity(
    opportunity_id: UUID,
    payload: OpportunityUpdateRequest,
    current: User = Depends(require_permission("manage_opportunities")),
) -> OpportunityResponse:
    async with async_session_factory() as session:
        repo = OpportunitiesRepository(session)
        opp = await repo.get_by_id(opportunity_id)
        if opp is None:
            _raise_not_found("Oportunidad")
        try:
            opp = await repo.update_stage(
                opp,
                stage=payload.stage,
                response_outcome=payload.response_outcome,
                note=payload.note,
                owner_user_id=current.id,
                author_for_note=current.display_name,
                contact_type=payload.contact_type,
            )
        except ValueError as exc:
            msg = str(exc)
            if msg == "invalid_stage":
                raise HTTPException(status_code=400, detail="Fase no válida.") from exc
            if msg == "invalid_response_outcome":
                raise HTTPException(status_code=400, detail="Respuesta (subestado) no válida.") from exc
            if msg == "stage_regression":
                raise HTTPException(
                    status_code=400,
                    detail="No se puede volver a una fase anterior.",
                ) from exc
            raise
        if payload.profile_cv is not None:
            updates = payload.profile_cv.model_dump(exclude_unset=True)
            if updates:
                opp = await repo.merge_profile_overrides(opp, updates, owner_user_id=current.id)
        await session.refresh(opp)
        owner = await _load_owner_user(session, opp)
    return _opportunity_to_response(opp, owner=owner, created=False)


@protected_router.post("/opportunities/{opportunity_id}/bitacora", response_model=OpportunityResponse)
async def post_opportunity_bitacora(
    opportunity_id: UUID,
    payload: OpportunityBitacoraRequest,
    current: User = Depends(require_permission("manage_opportunities")),
) -> OpportunityResponse:
    async with async_session_factory() as session:
        repo = OpportunitiesRepository(session)
        opp = await repo.get_by_id(opportunity_id)
        if opp is None:
            _raise_not_found("Oportunidad")
        author_raw = (payload.author or current.display_name).strip() or current.display_name
        opp = await repo.append_bitacora(
            opp, payload.text, author=author_raw, owner_user_id=current.id
        )
        await session.refresh(opp)
        owner = await _load_owner_user(session, opp)
        return _opportunity_to_response(opp, owner=owner, created=False)


@protected_router.put("/opportunities/{opportunity_id}/contacts", response_model=OpportunityResponse)
async def put_opportunity_contacts(
    opportunity_id: UUID,
    payload: OpportunityContactsReplaceRequest,
    current: User = Depends(require_permission("manage_opportunities")),
) -> OpportunityResponse:
    async with async_session_factory() as session:
        repo = OpportunitiesRepository(session)
        opp = await repo.get_by_id(opportunity_id)
        if opp is None:
            _raise_not_found("Oportunidad")
        contacts_in = [c.model_dump() for c in payload.contacts]
        opp = await repo.replace_contacts(opp, contacts_in, owner_user_id=current.id)
        await session.refresh(opp)
        owner = await _load_owner_user(session, opp)
        return _opportunity_to_response(opp, owner=owner, created=False)


@public_router.post("/auth/register", response_model=LoginResponse, status_code=201)
async def auth_register(payload: RegisterRequest) -> LoginResponse:
    settings = get_settings()
    if not settings.mle_open_registration:
        raise HTTPException(
            status_code=403,
            detail="El registro de nuevas cuentas está deshabilitado.",
        )
    async with async_session_factory() as session:
        repo = UsersRepository(session)
        if await repo.get_by_email(payload.email):
            raise HTTPException(status_code=400, detail="El correo ya está registrado.")
        u = await repo.create(
            email=payload.email.strip().lower(),
            password_hash=hash_password(payload.password),
            display_name=payload.display_name.strip(),
            role="user",
        )
        uid = u.id
        u_email = u.email
        u_display = u.display_name
        u_role = u.role
        token = create_access_token(user_id=uid)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserPublic(
            user_id=str(uid),
            email=u_email,
            display_name=u_display,
            role=u_role,
            permissions=[],
            is_active=True,
        ),
    )


@public_router.post("/auth/login", response_model=LoginResponse)
async def auth_login(payload: LoginRequest) -> LoginResponse:
    async with async_session_factory() as session:
        repo = UsersRepository(session)
        user = await repo.get_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Credenciales incorrectas.")
        if not user.is_active:
            raise HTTPException(status_code=401, detail="Cuenta inactiva.")
        uid = user.id
        email = user.email
        display_name = user.display_name
        role = user.role
        permissions = user.permissions if isinstance(user.permissions, list) else []
        token = create_access_token(user_id=uid)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserPublic(
            user_id=str(uid),
            email=email,
            display_name=display_name,
            role=role,
            permissions=permissions,
            is_active=True,
        ),
    )


def _user_to_public(u: User) -> UserPublic:
    return UserPublic(
        user_id=str(u.id),
        email=u.email,
        display_name=u.display_name,
        role=u.role,
        permissions=u.permissions if isinstance(u.permissions, list) else [],
        is_active=u.is_active,
    )


@protected_router.get("/auth/me", response_model=UserPublic)
async def auth_me(current: User = Depends(get_current_user)) -> UserPublic:
    return _user_to_public(current)


@protected_router.get("/admin/users", response_model=AdminUsersListResponse)
async def admin_list_users(_admin: User = Depends(require_admin)) -> AdminUsersListResponse:
    async with async_session_factory() as session:
        repo = UsersRepository(session)
        users = await repo.list_all()
    return AdminUsersListResponse(items=[_user_to_public(u) for u in users])


VALID_PERMISSIONS = {"use_search", "manage_opportunities"}


@protected_router.post("/admin/users", response_model=UserPublic, status_code=201)
async def admin_create_user(
    payload: AdminCreateUserRequest, _admin: User = Depends(require_admin)
) -> UserPublic:
    perms = [p for p in payload.permissions if p in VALID_PERMISSIONS]
    async with async_session_factory() as session:
        repo = UsersRepository(session)
        if await repo.get_by_email(payload.email):
            raise HTTPException(status_code=400, detail="El correo ya está registrado.")
        u = await repo.create(
            email=payload.email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
            role=payload.role,
            permissions=perms,
        )
    return _user_to_public(u)


@protected_router.patch("/admin/users/{user_id}", response_model=UserPublic)
async def admin_update_user(
    user_id: UUID,
    payload: AdminUpdateUserRequest,
    admin: User = Depends(require_admin),
) -> UserPublic:
    perms = [p for p in payload.permissions if p in VALID_PERMISSIONS] if payload.permissions is not None else None
    async with async_session_factory() as session:
        repo = UsersRepository(session)
        if payload.email is not None:
            existing = await repo.get_by_email(payload.email)
            if existing and existing.id != user_id:
                raise HTTPException(status_code=400, detail="El correo ya está registrado.")
        u = await repo.update(
            user_id,
            email=payload.email,
            display_name=payload.display_name,
            role=payload.role,
            is_active=payload.is_active,
            permissions=perms,
        )
        if u is None:
            _raise_not_found("Usuario")
    return _user_to_public(u)


@protected_router.delete("/admin/users/{user_id}", status_code=204)
async def admin_delete_user(
    user_id: UUID,
    admin: User = Depends(require_admin),
) -> Response:
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo.")
    async with async_session_factory() as session:
        repo = UsersRepository(session)
        deleted = await repo.delete(user_id)
        if not deleted:
            _raise_not_found("Usuario")
    return Response(status_code=204)


@protected_router.delete("/opportunities/{opportunity_id}", status_code=204)
async def delete_opportunity(
    opportunity_id: UUID,
    _current: User = Depends(require_permission("manage_opportunities")),
) -> Response:
    async with async_session_factory() as session:
        repo = OpportunitiesRepository(session)
        opp = await repo.get_by_id(opportunity_id)
        if opp is None:
            _raise_not_found("Oportunidad")
        await session.delete(opp)
        await session.commit()
    return Response(status_code=204)


# ============================================================================
# DIRECTORIES — Directorios compartidos con steps custom
# ============================================================================


async def _directory_to_read(repo: DirectoriesRepository, directory) -> DirectoryRead:
    steps = await repo.list_steps(directory.id)
    item_count = await repo.count_items_by_directory(directory.id)
    return repo.to_read(directory, steps, item_count)


@protected_router.get("/directories", response_model=DirectoryListResponse)
async def list_directories(
    _u: User = Depends(require_permission("use_search")),
) -> DirectoryListResponse:
    async with async_session_factory() as session:
        repo = DirectoriesRepository(session)
        directories = await repo.list_all()
        items = [await _directory_to_read(repo, d) for d in directories]
    return DirectoryListResponse(items=items)


@protected_router.post("/directories", response_model=DirectoryRead, status_code=201)
async def create_directory(
    payload: DirectoryCreateRequest,
    current: User = Depends(require_permission("use_search")),
) -> DirectoryRead:
    async with async_session_factory() as session:
        repo = DirectoriesRepository(session)
        directory = await repo.create(
            name=payload.name,
            description=payload.description,
            created_by_user_id=current.id,
            steps=payload.steps,
        )
        return await _directory_to_read(repo, directory)


@protected_router.get("/directories/{directory_id}", response_model=DirectoryRead)
async def get_directory(
    directory_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> DirectoryRead:
    async with async_session_factory() as session:
        repo = DirectoriesRepository(session)
        directory = await repo.get(directory_id)
        if directory is None:
            _raise_not_found("Directorio")
        return await _directory_to_read(repo, directory)


@protected_router.patch("/directories/{directory_id}", response_model=DirectoryRead)
async def update_directory(
    directory_id: UUID,
    payload: DirectoryUpdateRequest,
    _u: User = Depends(require_permission("use_search")),
) -> DirectoryRead:
    async with async_session_factory() as session:
        repo = DirectoriesRepository(session)
        directory = await repo.update(
            directory_id,
            name=payload.name,
            description=payload.description,
        )
        if directory is None:
            _raise_not_found("Directorio")
        return await _directory_to_read(repo, directory)


@protected_router.delete("/directories/{directory_id}", status_code=204)
async def delete_directory(
    directory_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> Response:
    async with async_session_factory() as session:
        repo = DirectoriesRepository(session)
        ok = await repo.delete(directory_id)
        if not ok:
            _raise_not_found("Directorio")
    return Response(status_code=204)


@protected_router.post("/directories/{directory_id}/steps", response_model=DirectoryStepRead, status_code=201)
async def add_step(
    directory_id: UUID,
    payload: DirectoryStepCreate,
    _u: User = Depends(require_permission("use_search")),
) -> DirectoryStepRead:
    async with async_session_factory() as session:
        repo = DirectoriesRepository(session)
        directory = await repo.get(directory_id)
        if directory is None:
            _raise_not_found("Directorio")
        step = await repo.add_step(
            directory_id,
            name=payload.name,
            is_terminal=payload.is_terminal,
            is_won=payload.is_won,
        )
        return DirectoryStepRead(
            id=step.id,
            name=step.name,
            display_order=step.display_order,
            is_terminal=step.is_terminal,
            is_won=step.is_won,
            created_at=step.created_at,
        )


@protected_router.patch("/directories/{directory_id}/steps/{step_id}", response_model=DirectoryStepRead)
async def update_step(
    directory_id: UUID,
    step_id: UUID,
    payload: DirectoryStepUpdate,
    _u: User = Depends(require_permission("use_search")),
) -> DirectoryStepRead:
    async with async_session_factory() as session:
        repo = DirectoriesRepository(session)
        step = await repo.update_step(
            step_id,
            name=payload.name,
            is_terminal=payload.is_terminal,
            is_won=payload.is_won,
            display_order=payload.display_order,
        )
        if step is None or step.directory_id != directory_id:
            _raise_not_found("Step")
        return DirectoryStepRead(
            id=step.id,
            name=step.name,
            display_order=step.display_order,
            is_terminal=step.is_terminal,
            is_won=step.is_won,
            created_at=step.created_at,
        )


@protected_router.post("/directories/{directory_id}/steps/reorder", response_model=list[DirectoryStepRead])
async def reorder_steps(
    directory_id: UUID,
    payload: DirectoryStepReorder,
    _u: User = Depends(require_permission("use_search")),
) -> list[DirectoryStepRead]:
    async with async_session_factory() as session:
        repo = DirectoriesRepository(session)
        steps = await repo.reorder_steps(directory_id, payload.step_ids)
        return [
            DirectoryStepRead(
                id=s.id,
                name=s.name,
                display_order=s.display_order,
                is_terminal=s.is_terminal,
                is_won=s.is_won,
                created_at=s.created_at,
            )
            for s in steps
        ]


@protected_router.delete("/directories/{directory_id}/steps/{step_id}", status_code=204)
async def delete_step(
    directory_id: UUID,
    step_id: UUID,
    payload: StepDeleteRequest,
    _u: User = Depends(require_permission("use_search")),
) -> Response:
    async with async_session_factory() as session:
        repo = DirectoriesRepository(session)
        try:
            ok = await repo.delete_step(step_id, move_items_to_step_id=payload.move_items_to_step_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        if not ok:
            _raise_not_found("Step")
    return Response(status_code=204)


@protected_router.patch("/opportunities/{opportunity_id}/step", response_model=OpportunityResponse)
async def move_opportunity_step(
    opportunity_id: UUID,
    payload: OpportunityMoveStepRequest,
    _u: User = Depends(require_permission("use_search")),
) -> OpportunityResponse:
    async with async_session_factory() as session:
        dir_repo = DirectoriesRepository(session)
        opp = await dir_repo.move_opportunity(opportunity_id, payload.direction)
        if opp is None:
            raise HTTPException(
                status_code=409,
                detail="No se puede mover (opp terminada, sin directorio o step fuera de rango).",
            )
        opp_repo = OpportunitiesRepository(session)
        fresh = await opp_repo.get_by_id(opportunity_id)
        if fresh is None:
            _raise_not_found("Oportunidad")
        owner = await _load_owner_user(session, fresh)
        return _opportunity_to_response(fresh, owner=owner, created=False)


@protected_router.post("/opportunities/{opportunity_id}/terminate", response_model=OpportunityResponse)
async def terminate_opportunity(
    opportunity_id: UUID,
    payload: OpportunityTerminateRequest,
    _u: User = Depends(require_permission("use_search")),
) -> OpportunityResponse:
    async with async_session_factory() as session:
        dir_repo = DirectoriesRepository(session)
        opp = await dir_repo.terminate_opportunity(
            opportunity_id,
            outcome=payload.outcome,
            note=payload.note,
        )
        if opp is None:
            _raise_not_found("Oportunidad")
        opp_repo = OpportunitiesRepository(session)
        fresh = await opp_repo.get_by_id(opportunity_id)
        if fresh is None:
            _raise_not_found("Oportunidad")
        owner = await _load_owner_user(session, fresh)
        return _opportunity_to_response(fresh, owner=owner, created=False)


@protected_router.post("/opportunities/{opportunity_id}/reopen", response_model=OpportunityResponse)
async def reopen_opportunity(
    opportunity_id: UUID,
    _payload: OpportunityReopenRequest = OpportunityReopenRequest(),
    _u: User = Depends(require_permission("use_search")),
) -> OpportunityResponse:
    async with async_session_factory() as session:
        dir_repo = DirectoriesRepository(session)
        opp = await dir_repo.reopen_opportunity(opportunity_id)
        if opp is None:
            _raise_not_found("Oportunidad")
        opp_repo = OpportunitiesRepository(session)
        fresh = await opp_repo.get_by_id(opportunity_id)
        if fresh is None:
            _raise_not_found("Oportunidad")
        owner = await _load_owner_user(session, fresh)
        return _opportunity_to_response(fresh, owner=owner, created=False)


# Incluir sub-routers al final: si no, FastAPI copia public/protected *vacíos* y /api/v1/* devuelve 404.
from mle.api.url_scrape_routes import url_scrape_router

protected_router.include_router(url_scrape_router)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(public_router)
api_router.include_router(protected_router)
