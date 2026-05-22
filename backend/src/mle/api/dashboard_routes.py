from __future__ import annotations

from fastapi import APIRouter, Depends

from mle.api.dashboard_schemas import DashboardActivityResponse, DashboardPipelineResponse
from mle.api.deps import get_current_user
from mle.db.base import async_session_factory
from mle.db.models import User
from mle.repositories.dashboard_repository import DashboardRepository

dashboard_router = APIRouter(tags=["dashboard"])


@dashboard_router.get("/dashboard/pipeline", response_model=DashboardPipelineResponse)
async def get_pipeline_metrics(
    _current_user: User = Depends(get_current_user),
) -> DashboardPipelineResponse:
    async with async_session_factory() as session:
        repo = DashboardRepository(session)
        data = await repo.get_pipeline_metrics()
    return DashboardPipelineResponse(**data)


@dashboard_router.get("/dashboard/activity", response_model=DashboardActivityResponse)
async def get_activity_metrics(
    _current_user: User = Depends(get_current_user),
) -> DashboardActivityResponse:
    async with async_session_factory() as session:
        repo = DashboardRepository(session)
        data = await repo.get_activity_metrics()
    return DashboardActivityResponse(**data)
