from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ApiErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


SearchFocusLiteral = Literal["general", "linkedin", "instagram"]
ExaCategoryLiteral = Literal["people", "company"]


class SearchJobCreateRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    contact_channels: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)
    search_focus: SearchFocusLiteral | None = None
    exa_category: ExaCategoryLiteral | None = None
    exa_criteria: str | None = Field(default=None, max_length=1200)
    directory_id: UUID = Field(
        description="Directorio destino donde irán las oportunidades generadas por esta búsqueda."
    )


class SearchJobCreateResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime
    clarifying_question: str | None = None
    requires_clarification: bool = False


class ClarifySearchJobRequest(BaseModel):
    reply: str = Field(min_length=1, max_length=500)


class ClarifySearchJobResponse(BaseModel):
    job_id: str
    status: str


class SearchJobListItemResponse(BaseModel):
    job_id: str
    query: str
    status: str
    created_at: datetime
    exa_category: str | None = None
    directory_id: str | None = None
    directory_name: str | None = None
    error_message: str | None = None


class SearchJobsListResponse(BaseModel):
    items: list[SearchJobListItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SearchJobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    current_stage: str
    metrics: dict[str, int]
    quality_metrics: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime
    pipeline_mode: str | None = None
    exa_results_preview: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None
    exa_category: str | None = None
    exa_criteria: str | None = None
    query_text: str | None = None
    error_message: str | None = None
    awaiting_clarification: bool = False
    clarifying_question: str | None = None


class ProfileInterpretRequest(BaseModel):
    texts: list[str] = Field(default_factory=list, max_length=100)


class ProfileInterpretItemResponse(BaseModel):
    source_text: str
    normalized_name: str | None = None
    normalized_company: str | None = None
    normalized_specialty: str | None = None


class ProfileInterpretResponse(BaseModel):
    items: list[ProfileInterpretItemResponse]


class ProfileSummaryRequest(BaseModel):
    title: str = Field(default="", max_length=1000)
    specialty: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=500)
    snippet: str | None = Field(default=None, max_length=12000)


class ProfileSummaryExperienceItem(BaseModel):
    role: str
    organization: str | None = None
    period: str | None = None


class ProfileSummaryResponse(BaseModel):
    professional_summary: str | None = None
    company: str | None = None
    location: str | None = None
    about: str | None = None
    experiences: list[ProfileSummaryExperienceItem] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"
    notes: str | None = None


class UserPublic(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str
    permissions: list[str] = Field(default_factory=list)
    is_active: bool = True


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=160)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class AdminCreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=160)
    role: Literal["admin", "user"] = "user"
    permissions: list[str] = Field(default_factory=list)


class AdminUpdateUserRequest(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None
    permissions: list[str] | None = None


class AdminUsersListResponse(BaseModel):
    items: list[UserPublic]


class OpportunityOwnerSnippet(BaseModel):
    user_id: str
    display_name: str
    email: str


class ExaMoreResultsRequest(BaseModel):
    num_results: int = Field(default=40, ge=1, le=100)


class ExaMoreResultsResponse(BaseModel):
    ok: bool = True
    added_count: int = 0
    total_count: int = 0
    preview_count: int = 0
    query_used: str | None = None
    error: str | None = None


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


class DirectoryEntryItemResponse(BaseModel):
    entry_id: str
    display_title: str
    primary_url: str
    snippet: str | None = None
    entity_type: str
    city: str
    country: str
    created_at: datetime


class DirectoryEntriesListResponse(BaseModel):
    items: list[DirectoryEntryItemResponse]
    page: int
    page_size: int
    total: int


class OpportunityContactPayload(BaseModel):
    id: str | None = None
    kind: str = "other"
    value: str = ""
    note: str | None = None
    role: str | None = None
    is_primary: bool = False


class OpportunityResponse(BaseModel):
    opportunity_id: str
    job_id: str | None = None
    exa_preview_index: int | None = None
    directory_id: str | None = None
    current_step_id: str | None = None
    title: str
    source_url: str
    snippet: str | None = None
    specialty: str
    city: str
    stage: str
    response_outcome: str | None = None
    terminated_at: datetime | None = None
    terminated_outcome: str | None = None
    terminated_note: str | None = None
    contacts: list[dict[str, Any]]
    activity_timeline: list[dict[str, Any]]
    profile_overrides: dict[str, Any] = Field(default_factory=dict)
    contact_type: str | None = None
    created_at: datetime
    updated_at: datetime
    created: bool = False
    owner: OpportunityOwnerSnippet | None = None


class OpportunityEnrichResponse(BaseModel):
    status: str
    message: str = ""
    email: str = ""
    phone: str = ""
    whatsapp: str = ""
    address: str = ""
    schedule_text: str = ""
    website: str = ""
    facebook_url: str = ""
    instagram_url: str = ""
    linkedin_url: str = ""
    description: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)


class OpportunityListItemResponse(BaseModel):
    opportunity_id: str
    job_id: str | None = None
    exa_preview_index: int | None = None
    directory_id: str | None = None
    current_step_id: str | None = None
    title: str
    city: str
    stage: str
    response_outcome: str | None = None
    terminated_at: datetime | None = None
    terminated_outcome: str | None = None
    updated_at: datetime
    owner: OpportunityOwnerSnippet | None = None


class OpportunityListResponse(BaseModel):
    items: list[OpportunityListItemResponse]


class OpportunityCreateFromPreviewRequest(BaseModel):
    job_id: UUID
    exa_preview_index: int = Field(ge=1)


class OpportunityCreateManualRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    specialty: str = Field(default="", max_length=160)
    city: str = Field(default="", max_length=120)
    source_url: str = Field(default="", max_length=2000)
    snippet: str | None = Field(default=None, max_length=4000)


class OpportunityProfileCvPatch(BaseModel):
    """Valores editables en ficha; null elimina el override y vuelve al resumen generado."""

    about: str | None = Field(default=None, max_length=8000)
    location: str | None = Field(default=None, max_length=500)
    experiences: list[ProfileSummaryExperienceItem] | None = None


class OpportunityUpdateRequest(BaseModel):
    stage: str | None = Field(default=None, max_length=64)
    response_outcome: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=4000)
    profile_cv: OpportunityProfileCvPatch | None = None
    contact_type: Literal["employee", "company"] | None = None


class OpportunityBitacoraRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    author: str | None = Field(default=None, max_length=64)


class OpportunityContactsReplaceRequest(BaseModel):
    contacts: list[OpportunityContactPayload] = Field(default_factory=list)


# ---- URL Scraper ----


class UrlScrapeJobCreateRequest(BaseModel):
    target_url: str = Field(min_length=10, max_length=2000)
    user_prompt: str = Field(min_length=5, max_length=2000)
    directory_id: UUID | None = None


class UrlScrapeResultPreviewItem(BaseModel):
    index: int
    title: str
    url: str
    snippet: str | None = None
    city: str
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)


class UrlScrapeJobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    target_url: str
    directory_id: str | None = None
    entries_count: int = 0
    scrape_results_preview: list[UrlScrapeResultPreviewItem] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class UrlScrapeJobListItemResponse(BaseModel):
    job_id: str
    target_url: str
    status: str
    entries_count: int = 0
    created_at: datetime


class UrlScrapeJobsListResponse(BaseModel):
    items: list[UrlScrapeJobListItemResponse]


class UrlScrapeJobPushRequest(BaseModel):
    directory_id: UUID
    entry_indices: list[int] = Field(default_factory=list)

