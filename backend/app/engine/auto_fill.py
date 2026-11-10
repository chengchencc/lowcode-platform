"""发起时自动填充的系统字段（发起人 / 发起人所在部门）。

设计约束：
- 只作用于**顶层**人员/部门控件（表单校验已拦住子表列）；
- 值由服务端在提交/暂存时**强制写入**，不依赖前端传入，避免被篡改；
- 只在发起阶段填一次，后续审批节点按普通字段权限处理。
"""

from __future__ import annotations

from typing import Any

from app.core.constants import AutoFillSource, FieldType


def auto_fill_values(
    form_schema: Any,
    *,
    user_id: int | None,
    dept_id: int | None,
) -> dict[str, Any]:
    """按 schema 的 auto_fill 配置算出本次发起应写入的值。

    多选控件用单元素列表；部门缺失时跳过该字段（不写空值覆盖已有数据）。
    """
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
    return out


__all__ = ["auto_fill_values"]
