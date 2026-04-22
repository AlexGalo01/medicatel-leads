from __future__ import annotations

from pydantic import BaseModel, Field


class RelevanceCriteria(BaseModel):
    """Criterios estables para Exa (userLocation) y para el filtro post-búsqueda."""

    country_iso2: str | None = Field(default=None, max_length=2, description="ISO 3166-1 alpha-2 para Exa userLocation")
    city: str | None = None
    country_text: str | None = None
    role_or_stack_hint: str | None = None
    normalized_location: str | None = None


class ExaSearchConfig(BaseModel):
    query: str = Field(min_length=3, max_length=1200)
    type: str = Field(default="auto")
    num_results: int = Field(default=50, ge=1, le=100)
    use_highlights: bool = Field(default=True)
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    additional_queries: list[str] = Field(default_factory=list)
    exa_category: str | None = Field(default="people", max_length=32)


class PlannerOutput(BaseModel):
    search_config: ExaSearchConfig
    normalized_specialty: str
    normalized_location: str
    relevance_criteria: RelevanceCriteria = Field(default_factory=RelevanceCriteria)
    contact_channels: list[str] = Field(default_factory=list)
    planner_notes: str = Field(default="")

