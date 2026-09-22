"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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


def _register_engine_handlers(app: FastAPI) -> None:
    """把引擎异常映射成统一的错误体。

    `EngineError` 不属于 `AppError` 家族（引擎刻意不依赖 core.errors），
    如果不在这里接住，像「已通过的实例不可终止」这种正常的业务拒绝
    会变成 500 + 一大段 traceback —— 前端拿不到可判断的错误码，
    响应体也大到会让客户端读失败。

    注册点选在应用装配处（而不是 core/errors.py），因为只有这里
    可以同时引用 core 与 engine 而不破坏分层。
    """
    from app.engine.errors import EngineError, TokenConflict
    from app.engine.machine import IllegalTransition

    @app.exception_handler(IllegalTransition)
    async def _illegal_transition(_: Request, exc: IllegalTransition) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "ILLEGAL_TRANSITION",
                    "message": str(exc),
                    "extra": {"current": exc.current, "action": exc.action},
                }
            },
        )

    @app.exception_handler(TokenConflict)
    async def _token_conflict(_: Request, exc: TokenConflict) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": {"code": "TOKEN_CONFLICT", "message": str(exc)}},
        )

    @app.exception_handler(EngineError)
    async def _engine_error(_: Request, exc: EngineError) -> JSONResponse:
        # 兜底：流程定义问题（FlowInvalid）等 —— 对使用者来说都是「这次请求不成立」
        node_id = getattr(exc, "node_id", None)
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": type(exc).__name__.upper(),
                    "message": str(exc),
                    "extra": {"node_id": node_id} if node_id else {},
                }
            },
        )


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
    _register_engine_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"name": settings.app_name, "version": __version__, "docs": "/docs"}

    return app


app = create_app()
