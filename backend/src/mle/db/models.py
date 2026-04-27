from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, JSON, Text, UniqueConstraint
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
    directory_id: UUID | None = Field(default=None, index=True, foreign_key="directories.id")
    metadata_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class User(SQLModel, table=True):
    """Usuario del CRM (login y responsable de oportunidades)."""

    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    email: str = Field(index=True, unique=True, max_length=255)
    password_hash: str = Field(max_length=255)
    display_name: str = Field(max_length=160)
    role: str = Field(default="user", max_length=32)
    permissions: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, server_default="[]")
    )
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class Directory(SQLModel, table=True):
    """Directorio compartido del equipo que agrupa oportunidades con un flow de steps custom."""

    __tablename__ = "directories"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    name: str = Field(index=True, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    created_by_user_id: UUID | None = Field(default=None, index=True, foreign_key="users.id")
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class DirectoryStep(SQLModel, table=True):
    """Paso dentro del flow de un directorio. Orden estricto via display_order."""

    __tablename__ = "directory_steps"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    directory_id: UUID = Field(index=True, foreign_key="directories.id")
    name: str = Field(max_length=120)
    display_order: int = Field(index=True, default=0)
    is_terminal: bool = Field(default=False)
    is_won: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class Opportunity(SQLModel, table=True):
    """Oportunidad comercial. Vive dentro de un directorio y progresa por los steps del mismo."""

    __tablename__ = "opportunities"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    directory_id: UUID | None = Field(default=None, index=True, foreign_key="directories.id")
    current_step_id: UUID | None = Field(default=None, index=True, foreign_key="directory_steps.id")
    job_id: UUID | None = Field(default=None, index=True, foreign_key="search_jobs.id")
    exa_preview_index: int | None = Field(default=None, index=True)
    title: str = Field(default="", max_length=500)
    source_url: str = Field(default="", max_length=2000)
    snippet: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    specialty: str = Field(default="", max_length=160)
    city: str = Field(default="", max_length=120)
    # `stage` queda como columna legacy para compat con data existente; el flow real viene de current_step_id.
    stage: str = Field(default="first_contact", index=True, max_length=64)
    response_outcome: str | None = Field(default=None, max_length=32)
    terminated_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    terminated_outcome: str | None = Field(default=None, max_length=32)
    terminated_note: str | None = Field(default=None, max_length=500)
    contacts: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    activity_timeline: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    profile_overrides: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    contact_type: str | None = Field(default=None, max_length=32)
    owner_user_id: UUID | None = Field(default=None, index=True, foreign_key="users.id")
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class ExaRawEntry(SQLModel, table=True):
    """Fila cruda de directorio Exa (fase amplia) antes del lead enriquecido final.

    Anteriormente se llamaba DirectoryEntry; renombrado para liberar el nombre 'Directory'
    para el nuevo concepto de directorio compartido del equipo.
    """

    __tablename__ = "exa_raw_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    job_id: UUID = Field(index=True, foreign_key="search_jobs.id")
    display_title: str = Field(default="", max_length=500)
    primary_url: str = Field(default="", index=True, max_length=2000)
    snippet: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    entity_type: str = Field(default="", max_length=120)
    city: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=80)
    phones: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    emails: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    social_urls: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    field_confidence: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    raw_exa_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    created_at: datetime = Field(
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
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=500)
    schedule_text: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=500)
    facebook_url: str | None = Field(default=None, max_length=500)
    instagram_url: str | None = Field(default=None, max_length=500)
    primary_source_url: str | None = Field(default=None, max_length=500)
    exa_result_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    source_citations: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    enriched_sources: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
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
