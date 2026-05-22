from __future__ import annotations

from pydantic import BaseModel, Field


class StepMetric(BaseModel):
    step_id: str
    step_name: str
    directory_id: str
    directory_name: str
    count: int
    display_order: int


class ConversionStep(BaseModel):
    from_step: str
    to_step: str
    from_count: int
    to_count: int
    rate: float


class OwnerMetric(BaseModel):
    user_id: str
    display_name: str
    count: int


class AvgTimeStep(BaseModel):
    step_name: str
    avg_hours: float


class DashboardPipelineResponse(BaseModel):
    total_opportunities: int
    active_opportunities: int
    won_count: int
    lost_count: int
    overall_win_rate: float

    opportunities_by_step: list[StepMetric]
    conversion_rates: list[ConversionStep]
    won_lost: dict[str, int]
    response_outcomes: dict[str, int]
    by_owner: list[OwnerMetric]
    avg_time_per_step: list[AvgTimeStep]


class DailyCount(BaseModel):
    date: str
    count: int


class CategoryCount(BaseModel):
    name: str
    count: int


class ScoreRange(BaseModel):
    range: str
    count: int


class DashboardActivityResponse(BaseModel):
    total_searches: int
    avg_leads_per_search: float
    avg_lead_score: float

    search_jobs_by_status: dict[str, int]
    lead_score_distribution: list[ScoreRange]
    validation_rates: dict[str, int]

    by_import_source: dict[str, int]
    scrape_jobs_by_status: dict[str, int]
    top_scraping_sites: list[CategoryCount]

    contact_coverage: dict[str, float]

    opportunities_per_day: list[DailyCount]
    top_specialties: list[CategoryCount]
    top_cities: list[CategoryCount]
    top_countries: list[CategoryCount]
    active_directories: list[CategoryCount]
