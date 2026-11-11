"""发起时自动填充 / 默认值（发起人、发起部门、流程发起时间）。

设计约束：
- 只作用于**顶层**字段（表单校验已拦住子表列）；
- `auto_fill` 的值由服务端在提交/暂存时**强制写入**，发起阶段只读，客户端传值被丢弃；
- `default_source` 只是带入一个默认值，发起人仍然可以修改；
- 发起时间使用**本地时间**字符串，与表单里用户手选 datetime 的格式一致。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.constants import AutoFillSource, FieldType


def auto_fill_values(
    form_schema: Any,
    *,
    user_id: int | None,
    dept_id: int | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """按 schema 的 `auto_fill` 配置算出本次发起应强制写入的值。"""
    out: dict[str, Any] = {}
    for section in form_schema.sections:
        for field in section.fields:
            source = getattr(field, "auto_fill", None)
            if source is None:
                continue
            if source == AutoFillSource.INITIATOR:
                if user_id is None:
                    continue
                out[field.key] = (
                    [user_id] if field.type is FieldType.USER_MULTI else user_id
                )
            elif source == AutoFillSource.INITIATOR_DEPT:
                if dept_id is None:
                    continue
                out[field.key] = (
                    [dept_id] if field.type is FieldType.DEPT_MULTI else dept_id
                )
            elif source == AutoFillSource.START_TIME:
                moment = now or datetime.now()
                out[field.key] = moment.strftime("%Y-%m-%d %H:%M:%S")
    return out


def default_values(
    form_schema: Any,
    *,
    user_id: int | None,
    dept_id: int | None,
) -> dict[str, Any]:
    """按 schema 的 `default_source` 配置算出可修改的默认值。"""
    out: dict[str, Any] = {}
    for section in form_schema.sections:
        for field in section.fields:
            source = getattr(field, "default_source", None)
            if source is None:
                continue
            if source == AutoFillSource.INITIATOR:
                if user_id is None:
                    continue
                out[field.key] = (
                    [user_id] if field.type is FieldType.USER_MULTI else user_id
                )
            elif source == AutoFillSource.INITIATOR_DEPT:
                if dept_id is None:
                    continue
                out[field.key] = (
                    [dept_id] if field.type is FieldType.DEPT_MULTI else dept_id
                )
    return out


__all__ = ["auto_fill_values", "default_values"]
