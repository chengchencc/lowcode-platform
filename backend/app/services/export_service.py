"""归档导出（PRD F8.2）。

**为什么是 CSV 而不是 xlsx**：导出的用途是「把归档数据捞出来做统计/存档」，
CSV 足够且零依赖 —— 加 openpyxl 只为了生成一个单表工作簿不划算。
用 UTF-8 BOM 开头，Excel 双击打开不乱码（这是 Windows 上最常见的抱怨）。

**列怎么来**：一行实例 = 一行数据，列 = 该批实例用到的**全部字段**（含机制 C
运行中追加的动态字段）取并集。同一个流程模板下的实例列自然一致；跨模板导出时
各模板的字段会并列，没填的位置留空 —— 这比按模板分成多个 sheet 更简单，
也更容易丢进透视表。
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import DISPLAY_FIELD_TYPES
from app.engine.ext_fields import merge_ext_fields
from app.models import Department, FlowInstance, FlowTemplate, FormVersion, User

#: 一次导出的上限。超过就分批导，避免一个请求把内存和响应体撑爆。
MAX_EXPORT_ROWS = 5000

#: 前置的元信息列（与字段列区分开，永远排在最前面）
META_COLUMNS: tuple[tuple[str, str], ...] = (
    ("code", "单号"),
    ("title", "标题"),
    ("flow_template_name", "流程"),
    ("initiator_name", "发起人"),
    ("initiator_dept_name", "发起部门"),
    ("status_label", "状态"),
    ("round", "轮次"),
    ("started_at", "提交时间"),
    ("finished_at", "完成时间"),
)


def _instance_rows(db: Session, instances: Sequence[FlowInstance]) -> list[dict[str, Any]]:
    """把实例、模板名、发起人、部门名一次性查齐，避免逐行 N+1。"""
    if not instances:
        return []

    flow_ids = {i.flow_template_id for i in instances}
    user_ids = {i.initiator_id for i in instances}
    dept_ids = {i.initiator_dept_id for i in instances if i.initiator_dept_id}

    flows = {
        row.id: row.name
        for row in db.scalars(select(FlowTemplate).where(FlowTemplate.id.in_(flow_ids))).all()
    }
    users = {
        row.id: row.real_name
        for row in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    }
    depts = {
        row.id: row.name
        for row in db.scalars(select(Department).where(Department.id.in_(dept_ids))).all()
    }

    from app.core.constants import INSTANCE_STATUS_LABELS

    out: list[dict[str, Any]] = []
    for instance in instances:
        out.append({
            "code": instance.code,
            "title": instance.title,
            "flow_template_name": flows.get(instance.flow_template_id, ""),
            "initiator_name": users.get(instance.initiator_id, ""),
            "initiator_dept_name": depts.get(instance.initiator_dept_id or 0, ""),
            "status_label": INSTANCE_STATUS_LABELS.get(instance.status, instance.status),
            "round": instance.round,
            "started_at": _stamp(instance.started_at),
            # 驳回不写 finished_at，台账的「完成时间」取最后一次动作时间
            "finished_at": _stamp(instance.finished_at or instance.last_action_at),
            "values": instance.current_data or {},
        })
    return out


def _stamp(value: Any) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


def _stamp_any(value: Any) -> str:
    """InstanceOut 里时间是 ISO 字符串；归档查询里是 datetime。"""
    if not value:
        return ""
    if isinstance(value, str):
        return value.replace("T", " ")[:16]
    return _stamp(value)


def _safe_cell(value: Any) -> str:
    """R3：阻止 CSV 公式注入（Excel 会把 = + - @ 开头的单元格当公式）。"""
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _write_table(
    rows: list[list[Any]],
    columns: list[tuple[str, str]],
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        _safe_cell(label) for label in [label for _, label in META_COLUMNS] + [label for _, label in columns]
    )
    for row in rows:
        writer.writerow(_safe_cell(value) for value in row)
    # BOM：Excel 靠它认出 UTF-8，否则中文列名全是乱码
    return "﻿" + buffer.getvalue()


def build_csv(db: Session, instances: Sequence[FlowInstance]) -> str:
    """生成 CSV 文本（含 BOM）。`instances` 由调用方按权限过滤好。"""
    rows = _instance_rows(db, instances)

    # 列 = 各实例「模板字段 ⊕ 动态字段」的并集，按模板里的出现顺序排列
    columns: list[tuple[str, str]] = []
    label_maps: dict[str, dict[str, str]] = {}
    seen: set[str] = set()
    for instance in instances:
        schema = _schema_of(db, instance).model_dump(mode="json")
        instance_columns, instance_maps = _schema_columns(schema)
        for key, label in instance_columns:
            if key in seen:
                continue
            seen.add(key)
            columns.append((key, label))
        for key, mapping in instance_maps.items():
            label_maps.setdefault(key, mapping)

    table_rows: list[list[Any]] = []
    for row in rows:
        values = row["values"]
        line = [row[key] for key, _ in META_COLUMNS]
        for key, _ in columns:
            line.append(_cell(values, key, label_maps.get(key)))
        table_rows.append(line)
    return _write_table(table_rows, columns)


def build_csv_from_render(render: dict[str, Any]) -> str:
    """单实例导出：使用 render 已按查看者权限裁剪过的 schema/values（D-04）。

    归档实例的 render 权限已是全量可见；运行中则只导出可见字段。
    """
    info = render.get("instance") or {}
    schema = render.get("schema_data") or {}
    values = render.get("values") or {}

    columns, label_maps = _schema_columns(schema)

    from app.core.constants import INSTANCE_STATUS_LABELS

    meta = [
        info.get("code", ""),
        info.get("title", ""),
        info.get("flow_template_name", ""),
        info.get("initiator_name", ""),
        info.get("initiator_dept_name", ""),
        INSTANCE_STATUS_LABELS.get(info.get("status"), info.get("status", "")),
        info.get("round", ""),
        _stamp_any(info.get("started_at")),
        _stamp_any(info.get("finished_at")),
    ]
    line = [
        *meta,
        *(_cell(values, key, label_maps.get(key)) for key, _ in columns),
    ]
    return _write_table([line], columns)


def _option_map(options: Any) -> dict[str, str]:
    """{选项 value: 展示 label}，兼容 schema 里的 dict / 字符串选项。"""
    mapping: dict[str, str] = {}
    for option in options or []:
        if isinstance(option, dict):
            value = option.get("value")
            if value is None:
                continue
            label = option.get("label")
            mapping[str(value)] = str(label if label is not None else value)
        else:
            mapping[str(option)] = str(option)
    return mapping


def _field_label_map(field: dict[str, Any]) -> dict[str, str]:
    """选项类字段的 code → label；级联字段把各父级下的选项一起展开。"""
    labels = _option_map(field.get("options"))
    cascader = field.get("cascader") or {}
    if isinstance(cascader, dict):
        for options in (cascader.get("options_by_parent") or {}).values():
            labels.update(_option_map(options))
    return labels


def _schema_columns(
    schema: dict[str, Any],
) -> tuple[list[tuple[str, str]], dict[str, dict[str, str]]]:
    """从 schema 生成导出列与「选项 code → label」映射。"""
    columns: list[tuple[str, str]] = []
    label_maps: dict[str, dict[str, str]] = {}
    for section in schema.get("sections", []) or []:
        for field in section.get("fields", []) or []:
            field_type = field.get("type")
            if field_type in DISPLAY_FIELD_TYPES:
                continue
            key = field.get("key")
            if not key:
                continue
            label = field.get("label") or key
            columns.append((key, label))
            mapping = _field_label_map(field)
            if mapping:
                label_maps[key] = mapping
            for column in field.get("columns") or []:
                column_key = column.get("key")
                if not column_key:
                    continue
                ref = f"{key}.{column_key}"
                columns.append(
                    (ref, f"{label} · {column.get('label') or column_key}")
                )
                column_map = _field_label_map(column)
                if column_map:
                    label_maps[ref] = column_map
    return columns, label_maps


def _cell(
    values: dict[str, Any], ref: str, labels: dict[str, str] | None = None
) -> str:
    """取一个字段的值。子表列（`items.amount`）展开成多行，便于在 Excel 里读。"""
    if "." not in ref:
        return _text(values.get(ref), labels)

    table_key, column_key = ref.split(".", 1)
    rows = values.get(table_key)
    if not isinstance(rows, list):
        return ""
    parts = [
        _text(row.get(column_key), labels)
        for row in rows
        if isinstance(row, dict) and row.get(column_key) not in (None, "", [])
    ]
    return " | ".join(parts)


def _text(value: Any, labels: dict[str, str] | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (list, tuple)):
        return "、".join(_text(v, labels) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}={_text(v, labels)}" for k, v in value.items())
    if labels is not None:
        mapped = labels.get(str(value))
        if mapped is not None:
            return mapped
    return str(value)


def _schema_of(db: Session, instance: FlowInstance):
    """实例的渲染 schema = 模板 schema ⊕ 运行中追加的动态字段。"""
    from app.schemas.form_schema import parse_form_schema

    version = db.get(FormVersion, instance.form_version_id)
    if version is None:
        from app.schemas.form_schema import FormSchema

        return FormSchema.model_validate({"sections": []})
    return merge_ext_fields(parse_form_schema(version.schema), list(instance.ext_fields))


def csv_filename(prefix: str = "flowform-archive") -> str:
    from app.core.clock import utcnow

    return f"{prefix}-{utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
