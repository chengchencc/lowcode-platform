"""首页聚合接口（M11）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.dashboard import DashboardOverview
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["首页"])


@router.get("/overview", response_model=DashboardOverview, summary="首页概览")
def overview(db: DbSession, user: CurrentUser) -> dict:
    return dashboard_service.overview(db, user)
