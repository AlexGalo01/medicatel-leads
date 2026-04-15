from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


JobStatus = Literal["pending", "running", "completed", "error"]


class SearchJobCreate(BaseModel):
    specialty: str = Field(min_length=2, max_length=120)
    country: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=2, max_length=120)
    contact_channels: list[str] = Field(default_factory=list, max_length=3)
    notes: str | None = Field(default=None, max_length=500)


class SearchJobRead(BaseModel):
    id: UUID
    specialty: str
    country: str
    city: str
    status: JobStatus
    progress: int
    contact_channels: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class SearchJobMetrics(BaseModel):
    sources_visited: int = 0
    leads_extracted: int = 0
    leads_scored: int = 0


class SearchJobStatusRead(BaseModel):
    job_id: UUID
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    current_stage: str
    metrics: SearchJobMetrics
    updated_at: datetime

