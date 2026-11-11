"""探活接口。用于容器健康检查与前端启动时确认后端就绪。"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.core.deps import DbSession

router = APIRouter(tags=["健康检查"])


@router.get("/healthz", summary="存活探针")
def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/readyz", summary="就绪探针（含数据库连通性）")
def readyz(db: DbSession) -> dict:
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "version": __version__,
        # 直接从实际连接取方言名（sqlite / mysql / postgresql），
        # 免得再接一种库就要回来改这里
        "database": db.get_bind().dialect.name,
    }
