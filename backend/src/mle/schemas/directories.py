from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DirectoryStepRead(BaseModel):
    id: UUID
    name: str
    display_order: int
    is_terminal: bool
    is_won: bool
    created_at: datetime


class DirectoryStepCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    is_terminal: bool = False
    is_won: bool = False


class DirectoryStepUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    is_terminal: bool | None = None
    is_won: bool | None = None
    display_order: int | None = Field(default=None, ge=0)


class DirectoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    steps: list[DirectoryStepCreate] = Field(default_factory=list, min_length=1, max_length=20)


class DirectoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)


class DirectoryRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_by_user_id: UUID | None
    steps: list[DirectoryStepRead] = Field(default_factory=list)
    item_count: int = 0
    created_at: datetime
    updated_at: datetime


class DirectoryListResponse(BaseModel):
    items: list[DirectoryRead] = Field(default_factory=list)


class DirectoryStepReorder(BaseModel):
    """Reordena todos los steps de un directorio en una sola llamada."""

    step_ids: list[UUID] = Field(min_length=1)


class OpportunityMoveStepRequest(BaseModel):
    """Avanza/retrocede un item al step adyacente (±1)."""

    direction: str = Field(pattern="^(forward|backward)$")


class OpportunityTerminateRequest(BaseModel):
    outcome: str = Field(pattern="^(won|lost|no_response)$")
    note: str | None = Field(default=None, max_length=500)


class OpportunityReopenRequest(BaseModel):
    """Reabre una opportunity terminada — vuelve al current_step_id previo."""

    pass


class StepDeleteRequest(BaseModel):
    """Al borrar un step con items dentro, se piden a dónde moverlos."""

    move_items_to_step_id: UUID | None = None
