from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SearchJob(SQLModel, table=True):
    __tablename__ = "search_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    specialty: str = Field(index=True, max_length=120)
    country: str = Field(index=True, max_length=80)
    city: str = Field(index=True, max_length=120)
    status: str = Field(default="pending", index=True, max_length=32)
    progress: int = Field(default=0, ge=0, le=100)
    requested_contact_channels: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    notes: str | None = Field(default=None, max_length=500)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class Lead(SQLModel, table=True):
    __tablename__ = "leads"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    job_id: UUID = Field(index=True, foreign_key="search_jobs.id")
    full_name: str = Field(index=True, max_length=160)
    specialty: str = Field(index=True, max_length=120)
    country: str = Field(index=True, max_length=80)
    city: str = Field(index=True, max_length=120)
    organization_name: str | None = Field(default=None, max_length=200)
    score: float | None = Field(default=None, ge=0, le=10)
    score_reasoning: str | None = Field(default=None, max_length=1000)
    email: str | None = Field(default=None, max_length=255)
    whatsapp: str | None = Field(default=None, max_length=30)
    linkedin_url: str | None = Field(default=None, max_length=500)
    primary_source_url: str | None = Field(default=None, max_length=500)
    exa_result_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    source_citations: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    langsmith_metadata: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    validation_status: str = Field(default="pending", index=True, max_length=32)
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )

