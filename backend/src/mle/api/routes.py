from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from mle.api.schemas import (
    LeadCrmUpdateRequest,
    LeadDetailResponse,
    LeadItemResponse,
    LeadsExportRequest,
    LeadsExportResponse,
    LeadsListResponse,
    SearchJobCreateRequest,
    SearchJobCreateResponse,
    SearchJobStatusResponse,
)
from mle.db.base import async_session_factory
from mle.repositories.jobs_repository import JobsRepository
from mle.repositories.leads_repository import LeadsRepository
from mle.services.export_service import export_leads_to_csv
from mle.services.pipeline_service import run_job_pipeline
from mle.services.query_expansion_service import expand_user_search_query
from mle.services.lead_deep_enrich_service import deep_enrich_lead
from mle.core.config import get_settings
from mle.schemas.leads import LeadRead

api_router = APIRouter(prefix="/api/v1", tags=["mle"])


def _raise_not_found(entity_name: str) -> None:
    raise HTTPException(status_code=404, detail=f"{entity_name} no encontrado")


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


@api_router.post("/search-jobs", response_model=SearchJobCreateResponse, status_code=202)
async def create_search_job(payload: SearchJobCreateRequest) -> SearchJobCreateResponse:
    contact_channels = payload.contact_channels or ["email", "whatsapp", "linkedin"]
    user_query = payload.query.strip()
    expanded_query, expansion_meta = await expand_user_search_query(
        user_query=user_query,
        contact_channels=contact_channels,
        search_focus=payload.search_focus,
        notes=payload.notes,
    )
    job_metadata: dict[str, object] = {
        "query_text": expanded_query,
        "user_query": user_query,
        "query_expansion_metadata": expansion_meta,
    }

    async with async_session_factory() as session:
        jobs_repository = JobsRepository(session)
        created_job = await jobs_repository.create(
            expanded_query_text=expanded_query,
            requested_contact_channels=contact_channels,
            notes=payload.notes,
            metadata_json=job_metadata,
        )

    asyncio.create_task(run_job_pipeline(created_job.id))
    return SearchJobCreateResponse(
        job_id=str(created_job.id),
        status=created_job.status,
        created_at=created_job.created_at,
    )


@api_router.get("/search-jobs/{job_id}", response_model=SearchJobStatusResponse)
async def get_search_job_status(job_id: UUID) -> SearchJobStatusResponse:
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
    return SearchJobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress,
        current_stage=pipeline_stage,
        metrics=metrics,
        quality_metrics=quality_metrics,
        updated_at=job.updated_at,
    )


@api_router.get("/leads", response_model=LeadsListResponse)
async def list_leads(
    job_id: UUID = Query(...),
    min_score: float | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    contact_filter: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
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


@api_router.get("/leads/{lead_id}", response_model=LeadDetailResponse)
async def get_lead_detail(lead_id: UUID) -> LeadDetailResponse:
    async with async_session_factory() as session:
        leads_repository = LeadsRepository(session)
        lead = await leads_repository.get_by_id(lead_id)
        if lead is None:
            _raise_not_found("Lead")

    return _lead_read_to_detail(lead)


@api_router.post("/leads/{lead_id}/deep-enrich", response_model=LeadDetailResponse)
async def deep_enrich_lead_endpoint(lead_id: UUID) -> LeadDetailResponse:
    updated = await deep_enrich_lead(lead_id)
    if updated is None:
        _raise_not_found("Lead")
    return _lead_read_to_detail(updated)


@api_router.patch("/leads/{lead_id}/crm", response_model=LeadDetailResponse)
async def update_lead_crm(lead_id: UUID, payload: LeadCrmUpdateRequest) -> LeadDetailResponse:
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


@api_router.post("/leads/export", response_model=LeadsExportResponse)
async def export_leads(payload: LeadsExportRequest) -> LeadsExportResponse:
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


@api_router.get("/leads/export/file")
async def export_leads_file(
    job_id: UUID = Query(...),
    min_score: float | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    contact_filter: str | None = Query(default=None, max_length=40),
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

