"""审计查询 DTO（F6.6）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    # 直接从 ORM 对象构造（审计行字段与模型一一对应，无需手工映射）
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None = None
    actor_name: str | None = None
    biz_type: str
    biz_id: int
    action: str
    summary: str | None = None
    detail: dict[str, Any] | None = None
    ip: str | None = None
    created_at: datetime
