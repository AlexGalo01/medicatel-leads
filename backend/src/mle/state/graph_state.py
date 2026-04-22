from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class GraphLeadItem:
    lead_id: UUID | None = None
    full_name: str = ""
    specialty: str = ""
    city: str = ""
    country: str = ""
    score: float | None = None
    score_reasoning: str | None = None
    email: str | None = None
    whatsapp: str | None = None
    linkedin_url: str | None = None
    source_citations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class LeadSearchGraphState:
    job_id: UUID
    query_text: str
    status: str = "pending"
    current_stage: str = "planner"
    progress: int = 0
    search_plan: dict[str, Any] = field(default_factory=dict)
    planner_output: dict[str, Any] = field(default_factory=dict)
    exa_raw_results: list[dict[str, Any]] = field(default_factory=list)
    leads: list[GraphLeadItem] = field(default_factory=list)
    discarded_leads: list[dict[str, Any]] = field(default_factory=list)
    contact_coverage: float = 0.0
    missing_contact_count: int = 0
    retry_used: bool = False
    langsmith_metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

