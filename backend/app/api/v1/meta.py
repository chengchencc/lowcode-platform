"""应用元信息。公开接口：登录页、浏览器标题等未登录场景也要读。

系统名称只从后端配置 `APP_NAME` 取，前端不再硬编码 ——
上线时改一个环境变量即可，不用重新构建前端。
"""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.core.config import settings

router = APIRouter(tags=["应用信息"])


@router.get("/meta", summary="应用元信息（系统名称 / 版本）")
def get_meta() -> dict:
    """不含任何敏感配置，可匿名访问。"""
    return {"name": settings.app_name, "version": __version__}
