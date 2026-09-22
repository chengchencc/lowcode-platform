"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError, ProgrammingError

from app import __version__
from app.api.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.db.session import SessionLocal
from app.seeds.init_admin import run_seed

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

API_DESCRIPTION = """
面向单组织内部的低代码表单 + 审批流平台。

**M1 已实现**：认证、用户 / 部门 / 角色管理、操作审计。

约定：所有接口前缀 `/api/v1`；认证走 `Authorization: Bearer <access_token>`；
错误响应固定为 `{"detail": {"code", "message", "extra"?}}`。
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _bootstrap()
    yield


def _bootstrap() -> None:
    """启动时初始化种子数据。表结构由 alembic 管理，不在这里建表。"""
    try:
        with SessionLocal() as db:
            run_seed(db, settings)
    except (OperationalError, ProgrammingError):
        # 最常见的原因是还没跑迁移。给出可执行的提示，而不是甩一段堆栈。
        logger.error(
            "初始化失败：数据表不存在或不可访问。请先执行迁移：\n"
            "    cd backend && alembic upgrade head"
        )
        raise


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        description=API_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        debug=settings.debug,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"name": settings.app_name, "version": __version__, "docs": "/docs"}

    return app


app = create_app()
