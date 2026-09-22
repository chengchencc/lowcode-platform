"""字段写入、公式重算与变更 diff（PRD §3.4 / §3.6）。

**只接受当前节点可编辑的字段**（决策 D3）：权限矩阵是唯一的准入依据，
不可编辑的键被静默忽略而不是报错 —— 保证幂等重放与「前端多发了一点东西」都安全。

**公式由服务端重算覆盖**（决策 D4）：前端算出来的值一律被这里的结果覆盖，
防止绕过前端校验伪造计算结果。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.engine.expressions import evaluate_schema_formulas
from app.engine.permissions import FieldPermission, column_ref


@dataclass(frozen=True, slots=True)
class FieldDiff:
    key: str
    label: str
    old: Any
    new: Any

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "old": self.old, "new": self.new}


def field_label_index(form_schema: Any) -> dict[str, str]:
    """{字段引用: 中文标签}，用于 diff 展示。"""
    labels: dict[str, str] = {}
    for section in form_schema.sections:
        for field in section.fields:
            labels[field.key] = field.label
            for col in getattr(field, "columns", []) or []:
                labels[column_ref(field.key, col.key)] = f"{field.label} · {col.label}"
    return labels


def _equal(a: Any, b: Any) -> bool:
    """宽松比较：1 与 "1" 视为相同（表单值常是字符串）。"""
    if a is None and b is None:
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if a in (None, "") and b in (None, ""):
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        pass
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b, strict=True))
    return a == b


def apply_field_patch(
    *,
    current: Mapping[str, Any],
    patch: Mapping[str, Any],
    permissions: Mapping[str, FieldPermission],
    form_schema: Any,
) -> tuple[dict[str, Any], list[FieldDiff]]:
    """把补丁应用到当前数据上。

    返回 `(新数据, 变更明细)`。
    - 只接受 `permissions[k].editable` 为真的键，其余**静默忽略**（不抛错）
    - 分区的字段与子表列都用同一套权限表判定
    - 公式字段的值不接受外部传入，由 `evaluate_schema_formulas` 统一算
    """
    labels = field_label_index(form_schema)
    values = dict(current)
    diffs: list[FieldDiff] = []

    subtables = [
        field
        for section in form_schema.sections
        for field in section.fields
        if field.type == "subtable"
    ]
    subtable_keys = {f.key for f in subtables}

    # ---- 标量字段 ----
    for key, incoming in patch.items():
        if key in subtable_keys:
            continue
        permission = permissions.get(key)
        if permission is None or not permission.editable:
            # 未知字段（可能是被删掉的字段，或前端多发的）或本节点不可编辑 → 静默忽略
            continue
        if _equal(values.get(key), incoming):
            continue
        diffs.append(FieldDiff(key, labels.get(key, key), values.get(key), incoming))
        values[key] = incoming

    # ---- 子表：逐列按权限吸收 ----
    for field in subtables:
        if field.key not in patch:
            continue
        permission = permissions.get(field.key)
        if permission is None or not permission.visible:
            continue
        incoming_rows = patch[field.key]
        if not isinstance(incoming_rows, list):
            continue

        new_rows = _apply_subtable_rows(
            existing=values.get(field.key),
            incoming=incoming_rows,
            subtable_key=field.key,
            columns=[c.key for c in field.columns or []],
            column_types={c.key: c.type.value for c in field.columns or []},
            permissions=permissions,
            allow_add_remove=permission.editable,
        )
        if not _equal(values.get(field.key), new_rows):
            diffs.append(
                FieldDiff(field.key, labels.get(field.key, field.key), values.get(field.key), new_rows)
            )
            values[field.key] = new_rows

    # ---- 公式重算：服务端是权威（决策 D4）----
    computed = evaluate_schema_formulas(form_schema, values)
    for key, value in computed.items():
        if key in values and _equal(values.get(key), value):
            continue
        diffs.append(FieldDiff(key, labels.get(key, key), values.get(key), value))
        values[key] = value

    return values, _dedupe_diffs(diffs)


def _apply_subtable_rows(
    *,
    existing: Any,
    incoming: list[Any],
    subtable_key: str,
    columns: list[str],
    column_types: Mapping[str, str],
    permissions: Mapping[str, FieldPermission],
    allow_add_remove: bool,
) -> list[dict[str, Any]]:
    """构造新的行数组。

    **每个单元格都单独过权限**，不可编辑的列一律从原行取值 ——
    只做整表替换会让客户端能往只读列里塞值。

    `allow_add_remove`（= 子表本体是否可编辑）决定能不能增删行。
    「表格只读、某一列可填」就是 allow_add_remove=False + 列可编辑。
    """
    rows = existing if isinstance(existing, list) else []
    editable_cols = {
        col
        for col in columns
        if (perm := permissions.get(column_ref(subtable_key, col))) is not None and perm.editable
        # 公式列永远只读 —— 值由 evaluate_schema_formulas 统一算
        and column_types.get(col) != "formula"
    }

    out: list[dict[str, Any]] = []
    for index, incoming_row in enumerate(incoming):
        if not isinstance(incoming_row, Mapping):
            continue
        has_old = index < len(rows) and isinstance(rows[index], Mapping)
        if not allow_add_remove and not has_old:
            continue   # 不允许新增行

        old_row = rows[index] if has_old else {}
        assert isinstance(old_row, Mapping)
        # 从原行出发，再吸收可编辑列 —— 这样未在 columns 里的额外键也能保留
        merged = dict(old_row)
        for col in columns:
            if col in editable_cols and col in incoming_row:
                merged[col] = incoming_row[col]
        out.append(merged)

    return out


def _dedupe_diffs(diffs: list[FieldDiff]) -> list[FieldDiff]:
    """同一字段可能被「用户输入」和「公式重算」各记一次，保留最后一次。"""
    merged: dict[str, FieldDiff] = {}
    order: list[str] = []
    for item in diffs:
        if item.key not in merged:
            order.append(item.key)
            merged[item.key] = item
        else:
            first = merged[item.key]
            merged[item.key] = FieldDiff(item.key, item.label, first.old, item.new)
    return [merged[k] for k in order]
