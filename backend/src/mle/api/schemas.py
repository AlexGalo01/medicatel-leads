from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ApiErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


class SearchJobCreateRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    contact_channels: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)


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
    created_at: datetime
    updated_at: datetime


class LeadsExportRequest(BaseModel):
    job_id: str
    format: str = "csv"
    filters: dict[str, Any] = Field(default_factory=dict)


class LeadsExportResponse(BaseModel):
    download_path: str
    generated_at: datetime

