from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class LeadContacts(BaseModel):
    email: str | None = None
    whatsapp: str | None = None
    linkedin_url: HttpUrl | None = None


class LeadSourceCitation(BaseModel):
    url: HttpUrl
    title: str
    confidence: str = Field(default="medium")


class LeadRead(BaseModel):
    id: UUID
    job_id: UUID
    full_name: str
    specialty: str
    country: str
    city: str
    organization_name: str | None = None
    score: float | None = Field(default=None, ge=0, le=10)
    score_reasoning: str | None = None
    contacts: LeadContacts
    primary_source_url: HttpUrl | None = None
    validation_status: str
    created_at: datetime
    updated_at: datetime


class LeadDetailRead(LeadRead):
    source_citations: list[LeadSourceCitation] = Field(default_factory=list)
    exa_result_json: dict[str, Any] = Field(default_factory=dict)
    langsmith_metadata: dict[str, Any] = Field(default_factory=dict)


class LeadsListRead(BaseModel):
    items: list[LeadRead] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0

