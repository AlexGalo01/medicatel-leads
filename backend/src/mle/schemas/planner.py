from __future__ import annotations

from pydantic import BaseModel, Field


class ExaSearchConfig(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    type: str = Field(default="deep")
    num_results: int = Field(default=25, ge=1, le=100)
    use_highlights: bool = Field(default=True)
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)


class PlannerOutput(BaseModel):
    search_config: ExaSearchConfig
    normalized_specialty: str
    normalized_location: str
    contact_channels: list[str] = Field(default_factory=list)
    planner_notes: str = Field(default="")

