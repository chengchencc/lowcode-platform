"""条件表达式求值（PRD F2.4）。

结构是嵌套的 and/or 组，叶子是比较条件。**不用 `eval`** —— 同公式引擎的理由：
条件来自设计器配置，属于用户输入。

容错原则（与 §3.5 的设计一致）：**字段缺失一律视为「不匹配」，绝不抛错**。
表单还没填完时求值条件是很正常的场景，不该因此让流程推进失败。
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.flow_definition import Branch, Condition, ConditionGroup

#: 缺失值的哨兵，用于区分「字段不存在」与「字段值就是 None」
_MISSING = object()


def _get(values: Mapping[str, Any], field: str) -> Any:
    """取字段值，支持子表列的 `items[].amount` 记法（取第一行 —— 条件判断汇总时用不上）。"""
    if "[]." in field:
        table_key, column_key = field.split("[].", 1)
        rows = values.get(table_key)
        if isinstance(rows, list) and rows:
            first = rows[0]
            if isinstance(first, Mapping):
                return first.get(column_key, _MISSING)
        return _MISSING
    if field in values:
        return values[field]
    return _MISSING


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value is _MISSING or value == "":
        return None
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except (InvalidOperation, AttributeError):
            return None
    return None


def _is_empty(value: Any) -> bool:
    if value is _MISSING or value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict, set, tuple)):
        return len(value) == 0
    return False


def _compare(left: Any, cmp: str, right: Any) -> bool:
    """单次比较。类型不匹配时返回 False 而不是抛错。"""
    if cmp == "is_empty":
        return _is_empty(left)
    if cmp == "is_not_empty":
        return not _is_empty(left)

    # 缺失值：除了空值判断，其余一律不匹配
    if left is _MISSING or left is None:
        return False

    if cmp == "in":
        if not isinstance(right, (list, tuple, set)):
            return False
        return any(_equals(left, item) for item in right)
    if cmp == "not_in":
        if not isinstance(right, (list, tuple, set)):
            return True
        return not any(_equals(left, item) for item in right)
    if cmp == "contains":
        # left 是数组（复选/多选）时判断包含
        if isinstance(left, (list, tuple, set)):
            return any(_equals(item, right) for item in left)
        return isinstance(left, str) and isinstance(right, str) and right in left

    if cmp in {"==", "!="}:
        equal = _equals(left, right)
        return equal if cmp == "==" else not equal

    if cmp in {">", ">=", "<", "<="}:
        left_num, right_num = _to_decimal(left), _to_decimal(right)
        if left_num is None or right_num is None:
            # 退化成字符串比较（如日期 "2026-09-01" 也适用字典序）
            left_s, right_s = str(left), str(right)
            if cmp == ">":
                return left_s > right_s
            if cmp == ">=":
                return left_s >= right_s
            if cmp == "<":
                return left_s < right_s
            return left_s <= right_s
        if cmp == ">":
            return left_num > right_num
        if cmp == ">=":
            return left_num >= right_num
        if cmp == "<":
            return left_num < right_num
        return left_num <= right_num

    return False


def _equals(left: Any, right: Any) -> bool:
    """宽松相等：数字与数字字符串视为相等（表单值常是字符串）。"""
    if left is _MISSING:
        return False
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) is bool(right)
    left_num, right_num = _to_decimal(left), _to_decimal(right)
    if left_num is not None and right_num is not None:
        return left_num == right_num
    if isinstance(left, (list, tuple, set)) or isinstance(right, (list, tuple, set)):
        left_list = list(left) if isinstance(left, (list, tuple, set)) else [left]
        right_list = list(right) if isinstance(right, (list, tuple, set)) else [right]
        return len(left_list) == len(right_list) and all(
            _equals(a, b) for a, b in zip(left_list, right_list, strict=True)
        )
    return str(left) == str(right)


def evaluate_condition(condition: Condition, values: Mapping[str, Any]) -> bool:
    return _compare(_get(values, condition.field), condition.cmp, condition.value)


def evaluate_group(group: ConditionGroup, values: Mapping[str, Any]) -> bool:
    """求值一个条件组。空组的语义：and 视为真（无约束），or 视为假。"""
    results = [
        evaluate_condition(item, values)
        if isinstance(item, Condition)
        else evaluate_group(item, values)
        for item in group.conditions
    ]
    if not results:
        return group.op == "and"
    return all(results) if group.op == "and" else any(results)


def pick_branch(branches: list[Branch], values: Mapping[str, Any]) -> Branch | None:
    """按声明序求值，返回第一条命中的分支。

    `when=None` 的分支是「否则」，必然命中 —— 因此只要有 else 就一定有结果。
    全不命中且无 else 时返回 None，调用方应视为「直接跳过条件节点」。
    """
    for branch in branches:
        if branch.when is None:
            return branch
        if evaluate_group(branch.when, values):
            return branch
    return None
