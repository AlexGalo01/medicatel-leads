from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from mle.api.schemas import (
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
from mle.core.config import get_settings

api_router = APIRouter(prefix="/api/v1", tags=["mle"])


def _raise_not_found(entity_name: str) -> None:
    raise HTTPException(status_code=404, detail=f"{entity_name} no encontrado")


@api_router.post("/search-jobs", response_model=SearchJobCreateResponse, status_code=202)
async def create_search_job(payload: SearchJobCreateRequest) -> SearchJobCreateResponse:
    contact_channels = payload.contact_channels or ["email", "whatsapp", "linkedin"]

    async with async_session_factory() as session:
        jobs_repository = JobsRepository(session)
        created_job = await jobs_repository.create(
            query=payload.query,
            requested_contact_channels=contact_channels,
            notes=payload.notes,
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
    return SearchJobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        progress=job.progress,
        current_stage=pipeline_stage,
        metrics=metrics,
        updated_at=job.updated_at,
    )


@api_router.get("/leads", response_model=LeadsListResponse)
async def list_leads(
    job_id: UUID = Query(...),
    min_score: float | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> LeadsListResponse:
    async with async_session_factory() as session:
        leads_repository = LeadsRepository(session)
        leads_page = await leads_repository.list_by_job(
            job_id=job_id,
            min_score=min_score,
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
        source_citations=[],
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


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

    async with async_session_factory() as session:
        leads_repository = LeadsRepository(session)
        leads_page = await leads_repository.list_by_job(
            job_id=job_id,
            min_score=parsed_min_score,
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

