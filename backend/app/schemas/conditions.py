"""条件表达式契约（流程分支与表单联动规则共用）。

从 `flow_definition.py` 抽出，避免表单规则为了复用条件结构而反向依赖流程定义。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Comparison = Literal[
    "==", "!=", ">", ">=", "<", "<=", "in", "not_in", "contains", "is_empty", "is_not_empty"
]


class Condition(BaseModel):
    """单个比较条件。`field` 引用表单字段 key（子表列用 `items[].amount`）。"""

    field: str = Field(min_length=1, max_length=128)
    cmp: Comparison = "=="
    value: Any = None


class ConditionGroup(BaseModel):
    """条件组，支持 and/or 与嵌套（PRD F2.4）。

    `when` 为 null 表示「否则」分支（else），必须排在最后且只能有一个。
    """

    op: Literal["and", "or"] = "and"
    conditions: list[Condition | ConditionGroup] = Field(default_factory=list)


ConditionGroup.model_rebuild()


def referenced_fields(group: ConditionGroup) -> list[str]:
    """按声明序收集条件组里引用的全部字段（含嵌套组）。"""
    out: list[str] = []
    for item in group.conditions:
        if isinstance(item, Condition):
            out.append(item.field)
        else:
            out.extend(referenced_fields(item))
    return out


__all__ = ["Comparison", "Condition", "ConditionGroup", "referenced_fields"]
