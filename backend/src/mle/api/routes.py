from __future__ import annotations

import asyncio
import logging
import unicodedata
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
import json
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mle.api.deps import get_current_user, require_admin, require_permission
from mle.api.schemas import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    AdminUsersListResponse,
    AdminUserJobsResponse,
    PreviewLabelRequest,
    VALID_PREVIEW_LABELS,
    OpportunityCreateManualRequest,
    DirectoryEntriesListResponse,
    DirectoryEntryItemResponse,
    DirectorySourceCreateRequest,
    DirectorySourceItemResponse,
    DirectorySourcesListResponse,
    DirectorySourceUpdateRequest,
    ScrapingSiteCreateRequest,
    ScrapingSiteResponse,
    ScrapingSiteUpdateRequest,
    ScrapingSitesListResponse,
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
    PreviewContactPatch,
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
from mle.db.models import Opportunity, User, DirectoryStep
from mle.repositories.url_scrape_jobs_repository import UrlScrapeJobsRepository
from mle.repositories.directories_repository import DirectoriesRepository
from mle.repositories.directory_entries_repository import DirectoryEntriesRepository
from mle.repositories.jobs_repository import JobsRepository
from mle.repositories.leads_repository import LeadsRepository
from mle.repositories.opportunities_repository import OpportunitiesRepository
from mle.repositories.users_repository import UsersRepository
from mle.schemas.directories import (
    DirectoryCreateRequest,
    DirectoryDeleteRequest,
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
from mle.services.export_service import export_leads_to_csv, export_leads_to_xlsx, export_preview_to_xlsx
from mle.services.pipeline_service import run_job_pipeline
from mle.services.query_expansion_service import expand_user_search_query
from mle.services.exa_more_results_service import append_exa_results_for_job
from mle.services.profile_interpret_service import interpret_profile_texts
from mle.services.profile_interpret_service import extract_profile_summary
from mle.services.lead_deep_enrich_service import LeadCore, enrich_lead_contacts, EnrichmentResult
from mle.clients.exa_client import ExaClient
from mle.clients.brave_client import BraveSearchClient
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
        scrape_job_id=str(opp.scrape_job_id) if opp.scrape_job_id else None,
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
    current_user: User = Depends(require_permission("use_search")),
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
    if payload.exa_category in ("people", "company", "local_business"):
        plan_dict["exa_category"] = payload.exa_category

    job_metadata: dict[str, object] = {
        "query_text": expanded_query,
        "user_query": user_query,
        "query_expansion_metadata": expansion_meta,
        "search_plan": plan_dict,
    }
    if payload.exa_criteria and payload.exa_criteria.strip():
        job_metadata["exa_criteria"] = payload.exa_criteria.strip()
    if payload.exa_category in ("people", "company", "local_business"):
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
            user_id=current_user.id,
            scraping_site_ids=payload.scraping_site_ids or [],
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
        if exa_cat_client in ("people", "company", "local_business"):
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


@protected_router.patch("/search-jobs/{job_id}/preview/{preview_index}/label", status_code=200)
async def set_preview_item_label(
    job_id: UUID,
    preview_index: int,
    payload: PreviewLabelRequest,
    _u: User = Depends(require_permission("use_search")),
) -> dict[str, object]:
    """Establece o limpia la etiqueta de un ítem del preview Exa."""
    if payload.label is not None and payload.label not in VALID_PREVIEW_LABELS:
        raise HTTPException(status_code=422, detail=f"Etiqueta inválida. Valores permitidos: {sorted(VALID_PREVIEW_LABELS)}")
    async with async_session_factory() as session:
        repo = JobsRepository(session)
        job = await repo.get_by_id(job_id)
        if job is None:
            _raise_not_found("Job")
        meta = dict(job.metadata_json or {})
        preview = list(meta.get("exa_results_preview") or [])
        updated = False
        for item in preview:
            if isinstance(item, dict) and item.get("index") == preview_index:
                if payload.label is None:
                    item.pop("label", None)
                else:
                    item["label"] = payload.label
                updated = True
                break
        if not updated:
            raise HTTPException(status_code=404, detail="Ítem de preview no encontrado")
        meta["exa_results_preview"] = preview
        await repo.update_status(job_id=job_id, status=job.status, progress=job.progress, metadata_json=meta)
    return {"job_id": str(job_id), "preview_index": preview_index, "label": payload.label}


@protected_router.post("/search-jobs/{job_id}/cancel", status_code=200)
async def cancel_search_job(
    job_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> dict[str, str]:
    """Cancela un search job en ejecución o pendiente."""
    async with async_session_factory() as session:
        jobs_repository = JobsRepository(session)
        job = await jobs_repository.get_by_id(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job no encontrado")
        if job.status not in ("pending", "running"):
            raise HTTPException(status_code=409, detail="Solo se pueden cancelar jobs pendientes o en ejecución")
        await jobs_repository.update_status(job_id, "cancelled", job.progress)
    return {"status": "cancelled", "job_id": str(job_id)}


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

    suggested_urls_raw = job.metadata_json.get("suggested_source_urls")
    suggested_source_urls: list[dict[str, str]] = suggested_urls_raw if isinstance(suggested_urls_raw, list) else []

    sp = job.metadata_json.get("search_plan")
    exa_cat: str | None = None
    if isinstance(sp, dict):
        raw_cat = sp.get("exa_category")
        if raw_cat in ("people", "company", "local_business"):
            exa_cat = str(raw_cat)
        # Flujo unificado: company + use_places → reportar como local_business al frontend
        if exa_cat == "company" and sp.get("use_places"):
            exa_cat = "local_business"
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

    warnings_raw = job.metadata_json.get("warnings")
    warnings: list[str] = warnings_raw if isinstance(warnings_raw, list) else []

    lpa_preview_raw = job.metadata_json.get("lpa_preview")
    lpa_preview: list[dict[str, Any]] = lpa_preview_raw if isinstance(lpa_preview_raw, list) else []

    filter_stats: dict[str, Any] = {}
    for key in ("relevance_filter_kept", "relevance_filter_dropped",
                "relevance_filter_heuristic_drops", "relevance_filter_mode",
                "relevance_filter_discarded_sample", "relevance_filter_error"):
        if key in job.metadata_json:
            filter_stats[key] = job.metadata_json[key]

    activity_log_raw = job.metadata_json.get("activity_log")
    activity_log: list[dict[str, Any]] = activity_log_raw if isinstance(activity_log_raw, list) else []

    return SearchJobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress,
        current_stage=pipeline_stage,
        metrics=metrics,
        quality_metrics=quality_metrics,
        created_at=job.created_at,
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
        suggested_source_urls=suggested_source_urls,
        lpa_preview=lpa_preview,
        warnings=warnings,
        directory_id=str(job.directory_id) if job.directory_id else None,
        filter_stats=filter_stats,
        activity_log=activity_log,
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
        jobs_repo = JobsRepository(session)
        leads_page = await leads_repository.list_by_job(
            job_id=job_id,
            min_score=parsed_min_score,
            name_query=name_query,
            contact_filter=contact_filter,
            page=1,
            page_size=5000,
        )
        # Get job to extract query_text
        job = await jobs_repo.get_by_id(job_id)

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

    # Extract query text from job metadata
    query_text = None
    if job and isinstance(job.metadata_json, dict):
        query_text = str(job.metadata_json.get("user_query") or job.metadata_json.get("query_text") or "").strip() or None

    settings = get_settings()
    export_path = export_leads_to_csv(
        job_id=job_id,
        leads=leads_payload,
        export_dir_path=settings.export_dir,
        query_text=query_text,
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
        jobs_repo = JobsRepository(session)
        leads_page = await leads_repository.list_by_job(
            job_id=job_id,
            min_score=min_score,
            name_query=q,
            contact_filter=contact_filter,
            page=1,
            page_size=5000,
        )
        # Get job to extract query_text
        job = await jobs_repo.get_by_id(job_id)

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

    # Extract query text from job metadata
    query_text = None
    if job and isinstance(job.metadata_json, dict):
        query_text = str(job.metadata_json.get("user_query") or job.metadata_json.get("query_text") or "").strip() or None

    settings = get_settings()
    export_path_str = export_leads_to_csv(
        job_id=job_id,
        leads=leads_payload,
        export_dir_path=settings.export_dir,
        query_text=query_text,
    )
    export_path = Path(export_path_str)
    if not export_path.is_file():
        raise HTTPException(status_code=500, detail="No se pudo generar el archivo CSV")

    # Use the filename from export_path (which includes query and date)
    filename = export_path.name

    return FileResponse(
        path=str(export_path),
        filename=filename,
        media_type="text/csv; charset=utf-8",
    )


@protected_router.get("/leads/export/xlsx")
async def export_leads_xlsx_file(
    job_id: UUID = Query(...),
    min_score: float | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    contact_filter: str | None = Query(default=None, max_length=40),
    _u: User = Depends(require_permission("use_search")),
) -> FileResponse:
    async with async_session_factory() as session:
        leads_repository = LeadsRepository(session)
        jobs_repo = JobsRepository(session)
        leads_page = await leads_repository.list_by_job(
            job_id=job_id,
            min_score=min_score,
            name_query=q,
            contact_filter=contact_filter,
            page=1,
            page_size=5000,
        )
        # Get job to extract query_text
        job = await jobs_repo.get_by_id(job_id)

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
            "phone": lead.contacts.phone,
            "linkedin_url": str(lead.contacts.linkedin_url) if lead.contacts.linkedin_url else None,
            "address": lead.address,
            "schedule_text": lead.schedule_text,
            "primary_source_url": lead.primary_source_url,
        }
        for lead in leads_page.items
    ]

    # Extract query text from job metadata
    query_text = None
    if job and isinstance(job.metadata_json, dict):
        query_text = str(job.metadata_json.get("user_query") or job.metadata_json.get("query_text") or "").strip() or None

    settings = get_settings()
    export_path_str = export_leads_to_xlsx(
        job_id=job_id,
        leads=leads_payload,
        export_dir_path=settings.export_dir,
        query_text=query_text,
    )
    export_path = Path(export_path_str)
    if not export_path.is_file():
        raise HTTPException(status_code=500, detail="No se pudo generar el archivo Excel")

    # Use the filename from export_path (which includes query and date)
    filename = export_path.name

    return FileResponse(
        path=str(export_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@protected_router.get("/jobs/{job_id}/export/preview/xlsx")
async def export_preview_xlsx_file(
    job_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> FileResponse:
    """Export exa_results_preview (search-only mode) to Excel."""
    async with async_session_factory() as session:
        jobs_repo = JobsRepository(session)
        job = await jobs_repo.get_by_id(job_id)
        if job is None:
            _raise_not_found("Job")

    # Extract query text from metadata
    query_text = str(job.metadata_json.get("user_query") or job.metadata_json.get("query_text") or "").strip() or None

    preview_raw = job.metadata_json.get("exa_results_preview", [])
    preview_rows = []
    if isinstance(preview_raw, list):
        for idx, row in enumerate(preview_raw):
            if isinstance(row, dict):
                preview_rows.append({
                    "index": idx + 1,
                    "title": row.get("title", ""),
                    "specialty": row.get("specialty", ""),
                    "city": row.get("city", ""),
                    "linkedin_url": row.get("linkedin_url", ""),
                    "url": row.get("url", ""),
                    "snippet": row.get("snippet", ""),
                })

    settings = get_settings()
    export_path_str = export_preview_to_xlsx(
        job_id=job_id,
        rows=preview_rows,
        export_dir_path=settings.export_dir,
        query_text=query_text,
    )
    export_path = Path(export_path_str)
    if not export_path.is_file():
        _raise_not_found("Export file")

    # Use the filename from export_path (which includes query and date)
    filename = export_path.name

    return FileResponse(
        path=str(export_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@protected_router.get("/jobs/{job_id}/preview/{index}/export/xlsx")
async def export_preview_result_xlsx(
    job_id: UUID,
    index: int,
    _u: User = Depends(require_permission("use_search")),
) -> FileResponse:
    """Exportar un resultado preview individual a Excel."""
    async with async_session_factory() as session:
        jobs_repo = JobsRepository(session)
        job = await jobs_repo.get_by_id(job_id)
        if not job:
            _raise_not_found("Job")

        preview = job.metadata_json.get("exa_results_preview", []) if isinstance(job.metadata_json, dict) else []
        row = None
        for item in preview:
            if isinstance(item, dict) and item.get("index") == index:
                row = item
                break

        if not row:
            raise HTTPException(status_code=404, detail="Preview item no encontrado")

        # Extract query text from metadata for filename
        query_text = None
        if isinstance(job.metadata_json, dict):
            query_text = str(job.metadata_json.get("user_query") or job.metadata_json.get("query_text") or "").strip() or None

    settings = get_settings()
    export_path_str = export_preview_to_xlsx(
        job_id=job_id,
        rows=[row],
        export_dir_path=settings.export_dir,
        query_text=query_text,
    )
    export_path = Path(export_path_str)

    return FileResponse(
        path=str(export_path),
        filename=export_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@protected_router.get("/opportunities/{opportunity_id}/export/xlsx")
async def export_opportunity_xlsx(
    opportunity_id: UUID,
    _u: User = Depends(require_permission("manage_opportunities")),
) -> FileResponse:
    """Exportar una oportunidad individual a Excel (sin markdown)."""
    async with async_session_factory() as session:
        repo = OpportunitiesRepository(session)
        opp = await repo.get_by_id(opportunity_id)
        if not opp:
            _raise_not_found("Oportunidad")

        opp_data = {
            "title": opp.title,
            "specialty": opp.specialty,
            "city": opp.city,
            "stage": opp.stage,
            "source_url": opp.source_url,
            "snippet": opp.snippet,
            "response_outcome": opp.response_outcome,
            "contact_type": opp.contact_type,
            "contacts": [
                {
                    "kind": c.kind,
                    "value": c.value,
                    "note": c.note,
                }
                for c in opp.contacts
            ],
            "profile_overrides": opp.profile_overrides if isinstance(opp.profile_overrides, dict) else {},
            "created_at": opp.created_at.isoformat() if opp.created_at else None,
        }

    settings = get_settings()
    # Build filename from title and creation date
    title = str(opp.title).strip()[:50] if opp.title else "Oportunidad"
    if opp.created_at:
        date_str = opp.created_at.strftime("%d %m %Y")
        filename = f"{title} {date_str}.xlsx"
    else:
        filename = f"{title}.xlsx"

    export_path = settings.export_dir / filename

    # Use modified export_opportunity_to_xlsx that accepts custom filename
    from mle.services.export_service import _sanitize_filename
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    export_path.mkdir(parents=True, exist_ok=True)
    filename_safe = _sanitize_filename(filename)
    export_file = export_path.parent / filename_safe

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Oportunidad"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="6366F1", end_color="6366F1", fill_type="solid")

    row = 1
    fields = [
        ("Título", title),
        ("Especialidad", opp_data.get("specialty", "")),
        ("Ciudad", opp_data.get("city", "")),
        ("Etapa", opp_data.get("stage", "")),
        ("URL Fuente", opp_data.get("source_url", "")),
        ("Descripción", opp_data.get("snippet", "")),
        ("Resultado Respuesta", opp_data.get("response_outcome", "")),
        ("Contacto Tipo", opp_data.get("contact_type", "")),
    ]

    for label, value in fields:
        ws.cell(row=row, column=1, value=label).font = Font(bold=True)
        ws.cell(row=row, column=2, value=value or "")
        row += 1

    row += 1
    contacts_header = ws.cell(row=row, column=1, value="Contactos")
    contacts_header.font = header_font
    contacts_header.fill = header_fill
    row += 1

    contacts = opp_data.get("contacts", [])
    if contacts:
        ws.cell(row=row, column=1, value="Tipo").font = Font(bold=True)
        ws.cell(row=row, column=2, value="Valor").font = Font(bold=True)
        ws.cell(row=row, column=3, value="Nota").font = Font(bold=True)
        row += 1

        for contact in contacts:
            ws.cell(row=row, column=1, value=contact.get("kind", ""))
            ws.cell(row=row, column=2, value=contact.get("value", ""))
            ws.cell(row=row, column=3, value=contact.get("note", ""))
            row += 1

    profile = opp_data.get("profile_overrides", {})
    if profile:
        row += 1
        profile_header = ws.cell(row=row, column=1, value="Perfil")
        profile_header.font = header_font
        profile_header.fill = header_fill
        row += 1

        about = profile.get("about")
        if about:
            ws.cell(row=row, column=1, value="Acerca de").font = Font(bold=True)
            from mle.services.export_service import _strip_markdown
            ws.cell(row=row, column=2, value=_strip_markdown(about))
            row += 1

        location = profile.get("location")
        if location:
            ws.cell(row=row, column=1, value="Ubicación").font = Font(bold=True)
            ws.cell(row=row, column=2, value=location)
            row += 1

        experiences = profile.get("experiences", [])
        if experiences:
            ws.cell(row=row, column=1, value="Experiencias").font = Font(bold=True)
            row += 1
            for exp in experiences:
                role = exp.get("role", "")
                org = exp.get("organization", "")
                period = exp.get("period", "")
                exp_text = f"{role}"
                if org:
                    exp_text += f" - {org}"
                if period:
                    exp_text += f" ({period})"
                ws.cell(row=row, column=2, value=exp_text)
                row += 1

    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 40

    wb.save(export_file)

    return FileResponse(
        path=str(export_file),
        filename=filename_safe,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@protected_router.get("/directories/{directory_id}/opportunities/export/xlsx")
async def export_directory_opportunities_xlsx(
    directory_id: UUID,
    _u: User = Depends(require_permission("manage_opportunities")),
) -> FileResponse:
    """Exportar todas las oportunidades de un directorio a Excel."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from mle.services.export_service import _sanitize_filename, _strip_markdown

    async with async_session_factory() as session:
        # Fetch opportunities
        opp_repo = OpportunitiesRepository(session)
        opps = await opp_repo.list_opportunities(directory_id=directory_id, limit=5000)

        # Fetch directory steps for mapping
        dirs_repo = DirectoriesRepository(session)
        steps = await dirs_repo.list_steps(directory_id)
        steps_map = {s.id: s.name for s in steps}

        # Fetch owners
        owners = await _load_owners_map(session, opps)

    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Oportunidades"

    # Header styling
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="6366F1", end_color="6366F1", fill_type="solid")

    # Column headers
    headers = ["Nombre", "Especialidad", "Ciudad", "Teléfono", "Email", "Paso Actual", "Fuente", "Estado", "Propietario", "Actualizado"]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Data rows
    for row_idx, opp in enumerate(opps, start=2):
        # Nombre
        ws.cell(row=row_idx, column=1, value=opp.title or "—")
        # Especialidad
        ws.cell(row=row_idx, column=2, value=opp.specialty or "—")
        # Ciudad
        ws.cell(row=row_idx, column=3, value=opp.city or "—")
        # Teléfono
        phone = next((c.get("value") for c in (opp.contacts or []) if isinstance(c, dict) and c.get("kind") == "phone"), "—")
        ws.cell(row=row_idx, column=4, value=phone)
        # Email
        email = next((c.get("value") for c in (opp.contacts or []) if isinstance(c, dict) and c.get("kind") == "email"), "—")
        ws.cell(row=row_idx, column=5, value=email)
        # Paso Actual
        if opp.terminated_at:
            paso = "Terminada"
        else:
            paso = steps_map.get(opp.current_step_id) if opp.current_step_id else "—"
        ws.cell(row=row_idx, column=6, value=paso or "—")
        # Fuente
        source_label = {
            "excel": "Excel",
            "manual": "Manual",
            "search": "Búsqueda",
            "url_scrape": "Web",
        }.get(opp.import_source or "", opp.import_source or "—")
        ws.cell(row=row_idx, column=7, value=source_label)
        # Estado
        if opp.terminated_at:
            estado = "Ganada" if opp.terminated_outcome == "won" else "Perdida"
        else:
            estado = "Activa"
        ws.cell(row=row_idx, column=8, value=estado)
        # Propietario
        owner_name = owners.get(opp.owner_user_id).display_name if opp.owner_user_id and opp.owner_user_id in owners else "—"
        ws.cell(row=row_idx, column=9, value=owner_name)
        # Actualizado
        ws.cell(row=row_idx, column=10, value=opp.updated_at.isoformat() if opp.updated_at else "—")

    # Column widths
    ws.column_dimensions["A"].width = 30  # Nombre
    ws.column_dimensions["B"].width = 20  # Especialidad
    ws.column_dimensions["C"].width = 20  # Ciudad
    ws.column_dimensions["D"].width = 20  # Teléfono
    ws.column_dimensions["E"].width = 25  # Email
    ws.column_dimensions["F"].width = 18  # Paso
    ws.column_dimensions["G"].width = 12  # Fuente
    ws.column_dimensions["H"].width = 12  # Estado
    ws.column_dimensions["I"].width = 18  # Propietario
    ws.column_dimensions["J"].width = 20  # Actualizado

    # Save file
    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    filename = f"Oportunidades_{directory_id.hex[:8]}.xlsx"
    filename_safe = _sanitize_filename(filename)
    export_file = export_dir / filename_safe

    wb.save(export_file)

    return FileResponse(
        path=str(export_file),
        filename=filename_safe,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@protected_router.get("/directories/{directory_id}/entries/{entry_id}/export/xlsx")
async def export_directory_entry_xlsx(
    directory_id: UUID,
    entry_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> FileResponse:
    """Exportar una entrada de directorio a Excel."""
    async with async_session_factory() as session:
        entries_repo = DirectoryEntriesRepository(session)
        entry = await entries_repo.get_by_id(entry_id)
        if not entry:
            _raise_not_found("DirectoryEntry")

        entry_data = {
            "display_title": entry.display_title,
            "entity_type": entry.entity_type,
            "city": entry.city,
            "country": entry.country,
            "primary_url": str(entry.primary_url) if entry.primary_url else "",
            "snippet": entry.snippet,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }

    settings = get_settings()

    # Build filename from title and creation date
    title = str(entry.display_title).strip()[:50] if entry.display_title else "Entrada"
    if entry.created_at:
        date_str = entry.created_at.strftime("%d %m %Y")
        filename = f"{title} {date_str}.xlsx"
    else:
        filename = f"{title}.xlsx"

    from mle.services.export_service import _sanitize_filename, _strip_markdown
    import openpyxl
    from openpyxl.styles import Font

    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    filename_safe = _sanitize_filename(filename)
    export_file = export_dir / filename_safe

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Entrada"

    row = 1
    fields = [
        ("Título", entry_data.get("display_title", "")),
        ("Tipo Entidad", entry_data.get("entity_type", "")),
        ("Ciudad", entry_data.get("city", "")),
        ("País", entry_data.get("country", "")),
        ("URL Principal", entry_data.get("primary_url", "")),
        ("Descripción", _strip_markdown(entry_data.get("snippet", ""))),
    ]

    for label, value in fields:
        ws.cell(row=row, column=1, value=label).font = Font(bold=True)
        ws.cell(row=row, column=2, value=value or "")
        row += 1

    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 60

    wb.save(export_file)

    return FileResponse(
        path=str(export_file),
        filename=filename_safe,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@protected_router.patch("/jobs/{job_id}/preview/{index}/contact")
async def patch_preview_contact(
    job_id: UUID,
    index: int,
    payload: PreviewContactPatch,
    _u: User = Depends(require_permission("use_search")),
) -> dict[str, Any]:
    """Guardar datos de contacto validados en el preview item."""
    async with async_session_factory() as session:
        jobs_repo = JobsRepository(session)
        job = await jobs_repo.get_by_id(job_id)
        if not job:
            _raise_not_found("Job")

        meta = dict(job.metadata_json or {})
        preview = list(meta.get("exa_results_preview", []))

        updated = False
        for item in preview:
            if isinstance(item, dict) and item.get("index") == index:
                if payload.email is not None:
                    item["email"] = payload.email
                if payload.phone is not None:
                    item["phone"] = payload.phone
                if payload.whatsapp is not None:
                    item["whatsapp"] = payload.whatsapp
                if payload.source_urls is not None:
                    item["saved_source_urls"] = [str(u).strip() for u in payload.source_urls if str(u).strip()]
                updated = True
                break

        if not updated:
            raise HTTPException(status_code=404, detail="Preview item no encontrado")

        meta["exa_results_preview"] = preview
        await jobs_repo.update_status(job_id, job.status, job.progress, metadata_json=meta)
        return {"ok": True}


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
                job, payload.exa_preview_index, owner_user_id=current.id, contact_overrides=payload.contact_overrides
            )
        except ValueError as exc:
            if str(exc) == "preview_row_not_found":
                raise HTTPException(
                    status_code=400,
                    detail="No hay fila de vista previa Exa con ese índice para este job.",
                ) from exc
            raise HTTPException(status_code=400, detail="Datos de oportunidad no válidos.") from exc

        # If step_id is provided and this is a new opportunity, assign it to the step
        if payload.step_id and created:
            result = await session.execute(select(DirectoryStep).where(DirectoryStep.id == payload.step_id))
            step = result.scalars().first()
            if step is None:
                raise HTTPException(status_code=400, detail="El step especificado no existe.")
            opp.current_step_id = step.id
            opp.directory_id = step.directory_id
            await session.commit()
        elif created and opp.directory_id and not opp.current_step_id:
            # Auto-assign the first non-terminal step of the directory
            first_step_result = await session.execute(
                select(DirectoryStep)
                .where(DirectoryStep.directory_id == opp.directory_id, DirectoryStep.is_terminal == False)  # noqa: E712
                .order_by(DirectoryStep.display_order)
                .limit(1)
            )
            first_step = first_step_result.scalars().first()
            if first_step is not None:
                opp.current_step_id = first_step.id
                await session.commit()

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
        # Resolve step_id: if not provided but directory_id is, auto-assign first step
        resolved_step_id = payload.step_id
        if not resolved_step_id and payload.directory_id:
            first_step_result = await session.execute(
                select(DirectoryStep)
                .where(DirectoryStep.directory_id == payload.directory_id, DirectoryStep.is_terminal == False)  # noqa: E712
                .order_by(DirectoryStep.display_order)
                .limit(1)
            )
            first_step = first_step_result.scalars().first()
            if first_step is not None:
                resolved_step_id = first_step.id
        opp = await repo.create_manual(
            title=payload.title,
            specialty=payload.specialty,
            city=payload.city,
            source_url=payload.source_url,
            snippet=payload.snippet,
            owner_user_id=current.id,
            directory_id=payload.directory_id,
            current_step_id=resolved_step_id,
            contacts=[c.model_dump() for c in payload.contacts] if payload.contacts else [],
        )
        owner = await _load_owner_user(session, opp)
    return _opportunity_to_response(opp, owner=owner, created=True)


def _normalize_col(s: str) -> str:
    """Normaliza nombre de columna: minúsculas, sin acentos, sin espacios extra."""
    normalized = unicodedata.normalize("NFKD", s.lower().strip())
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    return normalized


def _find_column(headers: list[str], patterns: list[str]) -> int | None:
    """Encuentra índice de columna por patrones aproximados."""
    normalized_headers = [_normalize_col(h) for h in headers]
    for pattern in patterns:
        norm_pattern = _normalize_col(pattern)
        for idx, norm_header in enumerate(normalized_headers):
            if norm_pattern in norm_header or norm_header in norm_pattern:
                return idx
    return None


_XLSX_STATUS_TO_STAGE: dict[str, str | None] = {
    "primer contacto": "first_contact",
    "presentacion": "presentation",
    "presentación": "presentation",
    "esperando respuesta": "response",
    "en proceso": "response",
    "en espera documentacion": "documents_wait",
    "en espera documentación": "documents_wait",
    "en espera de documentacion": "documents_wait",
    "en espera de documentación": "documents_wait",
    "reunion agendada": "presentation",
    "reunión agendada": "presentation",
    "unido a red": None,
    "unido": None,
    "no unido": None,
    "no unidos": None,
    "descartado": None,
}

_XLSX_STAGE_LABELS: dict[str, str] = {
    "first_contact": "Primer Contacto",
    "presentation": "Reunión Agendada",
    "response": "Esperando Respuesta",
    "documents_wait": "En espera Documentación",
    "agreement_sign": "Firma de Acuerdo",
    "medicatel_profile": "Perfil Medicatel",
}

_XLSX_TERMINATED_STATUS = {"unido a red", "unido", "no unido", "no unidos", "descartado"}


def _parse_xlsx_file(contents: bytes) -> list[dict[str, Any]]:
    """Parsea un archivo Excel y retorna filas mapeadas sin guardar en BD.

    Cada fila tiene: row, title, specialty, city, phone, email, canal,
    stage, stage_label, terminated_outcome, response_outcome, comments, valid, error.
    """
    from io import BytesIO
    workbook = load_workbook(BytesIO(contents), data_only=True)
    ws = workbook.active

    # Detectar la fila de headers dinámicamente (puede haber títulos/subtítulos encima)
    header_row_idx = None
    headers = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), start=1):
        candidate = [str(c) if c is not None else "" for c in row]
        # Si alguna celda contiene "nombre" normalizado, es la fila de headers
        if any("nombre" in _normalize_col(c) for c in candidate):
            headers = candidate
            header_row_idx = row_idx
            break

    if not headers:
        raise ValueError("No se encontró la fila de encabezados en las primeras 15 filas.")

    col_nombre = _find_column(headers, ["nombre", "name", "contacto"])
    if col_nombre is None:
        raise ValueError("No se encontró columna 'Nombre' en el Excel.")

    col_especialidad = _find_column(headers, ["especialidad", "specialty"])
    col_ciudad = _find_column(headers, ["ciudad", "city", "departamento", "location"])
    col_telefono = _find_column(headers, ["telefono", "phone", "celular", "movil"])
    col_email = _find_column(headers, ["correo", "email", "mail"])
    col_canal = _find_column(headers, ["canal", "channel"])
    col_respondio = _find_column(headers, ["respondio", "respondió", "response", "respuesta"])
    col_status = _find_column(headers, ["status", "estado", "state"])
    col_comentarios = _find_column(headers, ["comentarios", "comments", "notas", "notes"])

    def _cell(row: tuple, idx: int | None) -> str:
        if idx is None or idx >= len(row):
            return ""
        val = row[idx]
        s = str(val).strip() if val is not None else ""
        return "" if s.lower() == "nan" else s

    parsed: list[dict[str, Any]] = []
    data_start_row = header_row_idx + 1
    for row_num, row in enumerate(ws.iter_rows(min_row=data_start_row, values_only=True), start=data_start_row):
        # Skip fully empty rows
        if all(c is None or str(c).strip() == "" for c in row):
            continue

        nombre = _cell(row, col_nombre)
        if not nombre:
            parsed.append({"row": row_num, "valid": False, "error": "Nombre vacío.", "title": ""})
            continue

        especialidad = _cell(row, col_especialidad)
        ciudad = _cell(row, col_ciudad)
        telefono = _cell(row, col_telefono)
        email = _cell(row, col_email)
        canal = _cell(row, col_canal)
        respondio = _cell(row, col_respondio)
        status = _cell(row, col_status)
        comentarios = _cell(row, col_comentarios)

        # Stage mapping
        stage = "first_contact"
        terminated_outcome = None
        if status:
            status_lower = status.lower().strip()
            if status_lower in _XLSX_TERMINATED_STATUS:
                terminated_outcome = "won" if status_lower in ("unido a red", "unido") else "lost"
            else:
                mapped = _XLSX_STATUS_TO_STAGE.get(status_lower)
                if mapped:
                    stage = mapped

        # Response outcome
        response_outcome = None
        if respondio:
            r = respondio.lower()
            if r in ("si", "sí", "yes", "true", "1"):
                response_outcome = "positive"
            elif r in ("no", "false", "0"):
                response_outcome = "negative"

        parsed.append({
            "row": row_num,
            "valid": True,
            "error": None,
            "title": nombre[:500],
            "specialty": especialidad[:160],
            "city": ciudad[:120],
            "phone": telefono,
            "email": email,
            "canal": canal,
            "stage": stage,
            "stage_label": _XLSX_STAGE_LABELS.get(stage, stage),
            "terminated_outcome": terminated_outcome,
            "response_outcome": response_outcome,
            "comments": comentarios,
        })

    return parsed


@protected_router.post("/opportunities/import/xlsx/preview")
async def preview_import_opportunities_xlsx(
    file: UploadFile = File(...),
    _current: User = Depends(require_permission("manage_opportunities")),
):
    """Parsea un archivo Excel y retorna las filas mapeadas sin guardar."""
    try:
        contents = await file.read()
        rows = _parse_xlsx_file(contents)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo Excel: {str(e)}")

    return {"rows": rows, "total": len(rows)}


@protected_router.post("/opportunities/import/xlsx")
async def import_opportunities_xlsx(
    file: UploadFile = File(...),
    directory_id: str = Query(...),
    target_step_id: str | None = Query(default=None),
    current: User = Depends(require_permission("manage_opportunities")),
):
    """Importa oportunidades desde un archivo Excel."""
    try:
        dir_id = UUID(directory_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="directory_id no es un UUID válido.")

    # Validate target_step_id if provided
    resolved_step_id = None
    if target_step_id:
        try:
            resolved_step_id = UUID(target_step_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="target_step_id no es un UUID válido.")

    try:
        contents = await file.read()
        rows = _parse_xlsx_file(contents)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo Excel: {str(e)}")

    created_count = 0
    skipped_count = 0
    errors: list[dict[str, Any]] = []

    async with async_session_factory() as session:
        now = datetime.now(timezone.utc)

        # Si no se proporciona target_step_id, usar el primer step del directorio
        if not resolved_step_id:
            first_step_result = await session.execute(
                select(DirectoryStep)
                .where(DirectoryStep.directory_id == dir_id, DirectoryStep.is_terminal == False)  # noqa: E712
                .order_by(DirectoryStep.display_order)
                .limit(1)
            )
            first_step = first_step_result.scalars().first()
            if not first_step:
                raise HTTPException(
                    status_code=400,
                    detail="El directorio no tiene pasos no-terminales. Selecciona un estado para importar.",
                )
            resolved_step_id = first_step.id

        logging.info(f"[IMPORT] directory_id={dir_id}, target_step_id={target_step_id}, resolved_step_id={resolved_step_id}, total_rows={len(rows)}")

        for parsed_row in rows:
            if not parsed_row["valid"]:
                skipped_count += 1
                errors.append({"row": parsed_row["row"], "reason": parsed_row["error"]})
                continue

            try:
                contacts = []
                if parsed_row.get("email"):
                    contacts.append({"kind": "email", "value": parsed_row["email"], "is_primary": True})
                if parsed_row.get("phone"):
                    contacts.append({"kind": "phone", "value": parsed_row["phone"], "is_primary": not contacts})

                # Si el usuario seleccionó target_step_id, ignorar terminated status del Excel
                if target_step_id:
                    terminated_at_val = None
                    terminated_outcome_val = None
                else:
                    terminated_at_val = now if parsed_row["terminated_outcome"] else None
                    terminated_outcome_val = parsed_row["terminated_outcome"]

                activity_timeline: list[dict[str, Any]] = [{
                    "at": now.isoformat(),
                    "stage": parsed_row["stage"],
                    "author": "sistema",
                    "text": "Oportunidad importada desde Excel.",
                }]
                if parsed_row.get("canal"):
                    activity_timeline[0]["canal"] = parsed_row["canal"]
                if parsed_row.get("comments"):
                    activity_timeline.append({
                        "at": now.isoformat(),
                        "stage": parsed_row["stage"],
                        "author": "sistema",
                        "text": f"Comentarios importados: {parsed_row['comments']}",
                    })

                opp = Opportunity(
                    title=parsed_row["title"],
                    specialty=parsed_row.get("specialty", ""),
                    city=parsed_row.get("city", ""),
                    stage=parsed_row["stage"],
                    response_outcome=parsed_row["response_outcome"],
                    terminated_outcome=terminated_outcome_val,
                    terminated_at=terminated_at_val,
                    contacts=contacts,
                    activity_timeline=activity_timeline,
                    directory_id=dir_id,
                    current_step_id=resolved_step_id,
                    owner_user_id=current.id,
                    import_source="excel",
                    created_at=now,
                    updated_at=now,
                )
                session.add(opp)
                created_count += 1
            except Exception as e:
                skipped_count += 1
                errors.append({"row": parsed_row["row"], "reason": f"Error: {str(e)[:100]}"})

        try:
            await session.commit()
            logging.info(f"[IMPORT] Commit successful: created={created_count}, skipped={skipped_count}")
        except Exception as e:
            logging.error(f"[IMPORT] Commit failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error al guardar oportunidades: {str(e)}")

    logging.info(f"[IMPORT] Response: created={created_count}, skipped={skipped_count}, errors={len(errors)}")
    return {"created": created_count, "skipped": skipped_count, "errors": errors}


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
        # Fetch target_url for any scrape-sourced opportunities
        scrape_ids = {o.scrape_job_id for o in rows if o.scrape_job_id}
        scrape_url_map: dict = {}
        if scrape_ids:
            scrape_repo = UrlScrapeJobsRepository(session)
            for sid in scrape_ids:
                sj = await scrape_repo.get_by_id(sid)
                if sj:
                    scrape_url_map[sj.id] = sj.target_url
    items = [
        OpportunityListItemResponse(
            opportunity_id=str(o.id),
            job_id=str(o.job_id) if o.job_id else None,
            scrape_job_id=str(o.scrape_job_id) if o.scrape_job_id else None,
            scrape_target_url=scrape_url_map.get(o.scrape_job_id) if o.scrape_job_id else None,
            exa_preview_index=o.exa_preview_index,
            directory_id=str(o.directory_id) if o.directory_id else None,
            current_step_id=str(o.current_step_id) if o.current_step_id else None,
            title=o.title,
            city=o.city,
            stage=o.stage,
            response_outcome=o.response_outcome,
            terminated_at=o.terminated_at,
            terminated_outcome=o.terminated_outcome,
            import_source=o.import_source,
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
    proposer = get_llm_client(st)
    reviewer = get_reviewer_llm_client(st)

    brave = None
    if st.brave_search_api_key and st.brave_search_enabled:
        brave = BraveSearchClient(
            api_key=st.brave_search_api_key,
            timeout_seconds=st.brave_search_timeout_seconds,
        )

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
                proposer=proposer,
                reviewer=reviewer,
                settings=st,
                brave=brave,
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
                        contact_sources=result.contact_sources,
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
        
        if payload.title is not None and payload.title.strip() and payload.title != opp.title:
            opp.title = payload.title.strip()
            session.add(opp)
            await session.commit()
            
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


@protected_router.get("/admin/users/{user_id}/jobs", response_model=AdminUserJobsResponse)
async def admin_list_user_jobs(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
) -> AdminUserJobsResponse:
    async with async_session_factory() as session:
        users_repo = UsersRepository(session)
        target_user = await users_repo.get_by_id(user_id)
        if target_user is None:
            _raise_not_found("Usuario")
        jobs_repo = JobsRepository(session)
        jobs, total = await jobs_repo.list_jobs(limit=limit, offset=offset, user_id=user_id)
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
        items.append(
            SearchJobListItemResponse(
                job_id=str(job.id),
                query=query_text or f"Búsqueda {str(job.id)[:8]}",
                status=job.status,
                created_at=job.created_at,
                exa_category=exa_category,
                directory_id=str(job.directory_id) if job.directory_id else None,
                directory_name=dir_name_map.get(job.directory_id) if job.directory_id else None,
                error_message=_pipeline_error_message(meta, max_length=160) if job.status == "error" else None,
            )
        )
    return AdminUserJobsResponse(items=items, total=total, user=_user_to_public(target_user))


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
        deleted = await repo.delete(user_id, deleted_by_user_id=admin.id)
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
        deleted = await repo.delete(opportunity_id, deleted_by_user_id=_current.id)
        if not deleted:
            _raise_not_found("Oportunidad")
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
    payload: DirectoryDeleteRequest = DirectoryDeleteRequest(),
    current_user: User = Depends(require_permission("use_search")),
) -> Response:
    async with async_session_factory() as session:
        repo = DirectoriesRepository(session)
        ok = await repo.delete(
            directory_id,
            deleted_by_user_id=current_user.id,
            reassign_to_directory_id=payload.reassign_to_directory_id,
        )
        if not ok:
            _raise_not_found("Directorio")
    return Response(status_code=204)


# ============================================================================
# DIRECTORY SOURCES — Referencias/scrapeo dentro de un directorio
# ============================================================================


@protected_router.get(
    "/directories/{directory_id}/sources",
    response_model=DirectorySourcesListResponse,
)
async def list_directory_sources(
    directory_id: UUID,
    status: str | None = Query(default=None, max_length=32),
    _u: User = Depends(require_permission("use_search")),
) -> DirectorySourcesListResponse:
    from mle.repositories.directory_sources_repository import (
        DirectorySourcesRepository,
    )

    async with async_session_factory() as session:
        repo = DirectorySourcesRepository(session)
        sources = await repo.list_by_directory(
            directory_id=directory_id, status=status
        )
    items = [
        DirectorySourceItemResponse(
            source_id=str(s.id),
            directory_id=str(s.directory_id),
            url=s.url,
            title=s.title,
            notes=s.notes,
            status=s.status,
            scrape_job_id=str(s.scrape_job_id) if s.scrape_job_id else None,
            source_search_job_id=str(s.source_search_job_id)
            if s.source_search_job_id
            else None,
            created_by_user_id=str(s.created_by_user_id)
            if s.created_by_user_id
            else None,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sources
    ]
    return DirectorySourcesListResponse(items=items)


@protected_router.post(
    "/directories/{directory_id}/sources",
    response_model=DirectorySourceItemResponse,
    status_code=201,
)
async def create_directory_source(
    directory_id: UUID,
    payload: DirectorySourceCreateRequest,
    current: User = Depends(require_permission("use_search")),
) -> DirectorySourceItemResponse:
    from mle.repositories.directory_sources_repository import (
        DirectorySourcesRepository,
    )

    async with async_session_factory() as session:
        repo = DirectorySourcesRepository(session)
        source = await repo.create(
            directory_id=directory_id,
            url=payload.url,
            title=payload.title,
            notes=payload.notes,
            source_search_job_id=payload.source_search_job_id,
            created_by_user_id=current.id,
        )
    return DirectorySourceItemResponse(
        source_id=str(source.id),
        directory_id=str(source.directory_id),
        url=source.url,
        title=source.title,
        notes=source.notes,
        status=source.status,
        scrape_job_id=str(source.scrape_job_id) if source.scrape_job_id else None,
        source_search_job_id=str(source.source_search_job_id)
        if source.source_search_job_id
        else None,
        created_by_user_id=str(source.created_by_user_id)
        if source.created_by_user_id
        else None,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


@protected_router.patch(
    "/directories/{directory_id}/sources/{source_id}",
    response_model=DirectorySourceItemResponse,
)
async def update_directory_source(
    directory_id: UUID,
    source_id: UUID,
    payload: DirectorySourceUpdateRequest,
    _u: User = Depends(require_permission("use_search")),
) -> DirectorySourceItemResponse:
    from mle.repositories.directory_sources_repository import (
        DirectorySourcesRepository,
    )

    async with async_session_factory() as session:
        repo = DirectorySourcesRepository(session)
        source = await repo.get_by_id(source_id)
        if source is None or source.directory_id != directory_id:
            _raise_not_found("Fuente")
        source = await repo.update(
            source_id,
            title=payload.title,
            notes=payload.notes,
            status=payload.status,
        )
    return DirectorySourceItemResponse(
        source_id=str(source.id),
        directory_id=str(source.directory_id),
        url=source.url,
        title=source.title,
        notes=source.notes,
        status=source.status,
        scrape_job_id=str(source.scrape_job_id) if source.scrape_job_id else None,
        source_search_job_id=str(source.source_search_job_id)
        if source.source_search_job_id
        else None,
        created_by_user_id=str(source.created_by_user_id)
        if source.created_by_user_id
        else None,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


@protected_router.delete(
    "/directories/{directory_id}/sources/{source_id}",
    status_code=204,
)
async def delete_directory_source(
    directory_id: UUID,
    source_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> Response:
    from mle.repositories.directory_sources_repository import (
        DirectorySourcesRepository,
    )

    async with async_session_factory() as session:
        repo = DirectorySourcesRepository(session)
        source = await repo.get_by_id(source_id)
        if source is None or source.directory_id != directory_id:
            _raise_not_found("Fuente")
        ok = await repo.delete(source_id, deleted_by_user_id=_u.id)
        if not ok:
            _raise_not_found("Fuente")
    return Response(status_code=204)


@protected_router.post(
    "/directories/{directory_id}/sources/{source_id}/scrape",
    status_code=202,
)
async def scrape_directory_source(
    directory_id: UUID,
    source_id: UUID,
    current: User = Depends(require_permission("use_search")),
) -> dict[str, str]:
    """Crea un URL scrape job a partir de una fuente guardada y la vincula."""
    from mle.repositories.directory_sources_repository import (
        DirectorySourcesRepository,
    )
    from mle.services.url_scrape_service import run_url_scrape_pipeline

    async with async_session_factory() as session:
        sources_repo = DirectorySourcesRepository(session)
        source = await sources_repo.get_by_id(source_id)
        if source is None or source.directory_id != directory_id:
            _raise_not_found("Fuente")

        scrape_jobs_repo = UrlScrapeJobsRepository(session)
        prompt = (
            f"Extraer profesionales y entidades del directorio: {source.title or source.url}"
        )
        scrape_job = await scrape_jobs_repo.create(
            target_url=source.url,
            user_prompt=prompt,
            directory_id=directory_id,
        )

        await sources_repo.update(
            source_id,
            status="scraping",
            scrape_job_id=scrape_job.id,
        )

        job_id = scrape_job.id

    asyncio.create_task(run_url_scrape_pipeline(job_id))

    return {
        "scrape_job_id": str(job_id),
        "status": "created",
        "source_id": str(source_id),
    }


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
            ok = await repo.delete_step(step_id, move_items_to_step_id=payload.move_items_to_step_id, deleted_by_user_id=_u.id)
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
        opp = await dir_repo.move_opportunity(opportunity_id, payload.step_id)
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


# ─── Scraping Sites (Global) ──────────────────────────────────────────────────


@protected_router.get("/scraping-sites", response_model=ScrapingSitesListResponse)
async def list_scraping_sites(_u: User = Depends(require_permission("use_search"))) -> ScrapingSitesListResponse:
    """List all scraping sites."""
    from mle.repositories.scraping_sites_repository import ScrapingSitesRepository

    async with async_session_factory() as session:
        repo = ScrapingSitesRepository(session)
        sites = await repo.list_all()
        return ScrapingSitesListResponse(
            items=[
                ScrapingSiteResponse(
                    site_id=str(s.id),
                    url=s.url,
                    title=s.title,
                    notes=s.notes,
                    scrape_prompt=s.scrape_prompt,
                    enrich_prompt=s.enrich_prompt,
                    last_scrape_job_id=str(s.last_scrape_job_id) if s.last_scrape_job_id else None,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
                for s in sites
            ]
        )


@protected_router.post("/scraping-sites", response_model=ScrapingSiteResponse, status_code=201)
async def create_scraping_site(
    payload: ScrapingSiteCreateRequest,
    current: User = Depends(require_permission("use_search")),
) -> ScrapingSiteResponse:
    """Create a new scraping site."""
    from mle.repositories.scraping_sites_repository import ScrapingSitesRepository

    async with async_session_factory() as session:
        repo = ScrapingSitesRepository(session)
        site = await repo.create(
            url=payload.url,
            title=payload.title,
            notes=payload.notes,
            scrape_prompt=payload.scrape_prompt,
            enrich_prompt=payload.enrich_prompt,
            created_by_user_id=current.id,
        )
        return ScrapingSiteResponse(
            site_id=str(site.id),
            url=site.url,
            title=site.title,
            notes=site.notes,
            scrape_prompt=site.scrape_prompt,
            enrich_prompt=site.enrich_prompt,
            last_scrape_job_id=str(site.last_scrape_job_id) if site.last_scrape_job_id else None,
            created_at=site.created_at,
            updated_at=site.updated_at,
        )


@protected_router.patch("/scraping-sites/{site_id}", response_model=ScrapingSiteResponse)
async def update_scraping_site(
    site_id: UUID,
    payload: ScrapingSiteUpdateRequest,
    _u: User = Depends(require_permission("use_search")),
) -> ScrapingSiteResponse:
    """Update a scraping site."""
    from mle.repositories.scraping_sites_repository import ScrapingSitesRepository

    async with async_session_factory() as session:
        repo = ScrapingSitesRepository(session)
        site = await repo.update(
            site_id,
            title=payload.title,
            notes=payload.notes,
            scrape_prompt=payload.scrape_prompt,
            enrich_prompt=payload.enrich_prompt,
        )
        if site is None:
            _raise_not_found("Sitio de scraping")
        return ScrapingSiteResponse(
            site_id=str(site.id),
            url=site.url,
            title=site.title,
            notes=site.notes,
            scrape_prompt=site.scrape_prompt,
            enrich_prompt=site.enrich_prompt,
            last_scrape_job_id=str(site.last_scrape_job_id) if site.last_scrape_job_id else None,
            created_at=site.created_at,
            updated_at=site.updated_at,
        )


@protected_router.delete("/scraping-sites/{site_id}", status_code=204)
async def delete_scraping_site(
    site_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> None:
    """Delete a scraping site."""
    from mle.repositories.scraping_sites_repository import ScrapingSitesRepository

    async with async_session_factory() as session:
        repo = ScrapingSitesRepository(session)
        deleted = await repo.delete(site_id)
        if not deleted:
            _raise_not_found("Sitio de scraping")


@protected_router.post("/scraping-sites/{site_id}/scrape", status_code=202)
async def scrape_scraping_site(
    site_id: UUID,
    _u: User = Depends(require_permission("use_search")),
) -> dict[str, str]:
    """Create a URL scrape job from a scraping site and return the job ID."""
    from mle.repositories.scraping_sites_repository import ScrapingSitesRepository
    from mle.services.url_scrape_service import run_url_scrape_pipeline

    async with async_session_factory() as session:
        sites_repo = ScrapingSitesRepository(session)
        site = await sites_repo.get(site_id)
        if site is None:
            _raise_not_found("Sitio de scraping")

        scrape_jobs_repo = UrlScrapeJobsRepository(session)
        base_prompt = site.scrape_prompt or f"Extraer profesionales y entidades del directorio: {site.title or site.url}"
        prompt = f"{base_prompt}\n\nNotas sobre la estructura de la página:\n{site.notes}" if site.notes else base_prompt
        scrape_job = await scrape_jobs_repo.create(
            target_url=site.url,
            user_prompt=prompt,
            directory_id=None,  # Global site, no directory initially
            scraping_site_id=site_id,
        )

        await sites_repo.set_last_scrape_job(site_id, scrape_job.id)

        job_id = scrape_job.id

    asyncio.create_task(run_url_scrape_pipeline(job_id))

    return {
        "scrape_job_id": str(job_id),
        "status": "created",
        "site_id": str(site_id),
    }


# Incluir sub-routers al final: si no, FastAPI copia public/protected *vacíos* y /api/v1/* devuelve 404.
from mle.api.url_scrape_routes import url_scrape_router

protected_router.include_router(url_scrape_router)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(public_router)
api_router.include_router(protected_router)
