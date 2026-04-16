from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


SearchFocusLiteral = Literal["general", "linkedin", "instagram"]


class SearchJobCreateRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    contact_channels: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)
    search_focus: SearchFocusLiteral | None = None


class SearchJobCreateResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime


class SearchJobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    current_stage: str
    metrics: dict[str, int]
    quality_metrics: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class LeadItemResponse(BaseModel):
    lead_id: str
    full_name: str
    specialty: str
    city: str
    score: float | None = None
    email: str | None = None
    whatsapp: str | None = None
    linkedin_url: str | None = None
    primary_source_url: str | None = None


class LeadsListResponse(BaseModel):
    items: list[LeadItemResponse]
    page: int
    page_size: int
    total: int


class LeadDetailResponse(LeadItemResponse):
    country: str
    score_reasoning: str | None = None
    validation_status: str
    source_citations: list[dict[str, Any]] = Field(default_factory=list)
    crm_stage: str = "new"
    crm_notes: str | None = None
    activity_timeline: list[dict[str, str]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    enrichment_status: str | None = None
    enrichment_message: str | None = None


class LeadCrmUpdateRequest(BaseModel):
    crm_stage: str | None = Field(default=None, max_length=32)
    crm_notes: str | None = Field(default=None, max_length=2000)
    activity_note: str | None = Field(default=None, max_length=500)


class LeadsExportRequest(BaseModel):
    job_id: str
    format: str = "csv"
    filters: dict[str, Any] = Field(default_factory=dict)


class LeadsExportResponse(BaseModel):
    download_path: str
    generated_at: datetime

