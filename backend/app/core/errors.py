"""统一错误模型与异常处理器。

错误响应体固定为：
    {"detail": {"code": "USER_NOT_FOUND", "message": "用户不存在", "extra": {...}}}

前端 `api/http.ts` 依赖这个形状做提示与分支处理，不要改动结构。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """业务异常基类。子类通过类属性声明默认状态码与错误码。"""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"
    message: str = "请求有误"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.extra = extra or {}
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        detail: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.extra:
            detail["extra"] = self.extra
        return {"detail": detail}


class BadRequestError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"
    message = "请求参数有误"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"
    message = "未登录或登录已失效"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    message = "没有权限执行该操作"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "资源不存在"


class ConflictError(AppError):
    """唯一键冲突、状态不允许、并发版本冲突等。"""

    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    message = "操作冲突"


class StaleVersionError(ConflictError):
    """乐观锁版本不匹配（决策 D5）。M3 引擎会大量用到。"""

    code = "STALE_VERSION"
    message = "数据已被他人修改，请刷新后重试"


class UnprocessableError(AppError):
    """请求格式正确但业务规则不允许（如：有人处理过之后不能撤回）。"""

    # 用字面量而非 status.HTTP_422_*：该常量在 starlette 新版被重命名过
    # （UNPROCESSABLE_ENTITY → UNPROCESSABLE_CONTENT），写死可跨版本稳定。
    status_code = 422
    code = "UNPROCESSABLE"
    message = "当前状态不允许该操作"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 把 pydantic 的错误压缩成 [{"field": "body.username", "message": "..."}]，
        # 前端直接逐条展示，不必理解 pydantic 的 loc 结构。
        errors = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ())),
                "message": err.get("msg", "格式不正确"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "VALIDATION_ERROR",
                    "message": "参数校验未通过",
                    "extra": {"errors": errors},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # FastAPI 内部（如 404 路由未命中、401 缺 Bearer）也统一成同一形状
        code = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
        }.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"code": code, "message": str(exc.detail)}},
        )
