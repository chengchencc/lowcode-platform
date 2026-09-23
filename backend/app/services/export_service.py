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
            "finished_at": _stamp(instance.finished_at),
            "values": instance.current_data or {},
        })
    return out


def _stamp(value: Any) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


def build_csv(db: Session, instances: Sequence[FlowInstance]) -> str:
    """生成 CSV 文本（含 BOM）。`instances` 由调用方按权限过滤好。"""
    rows = _instance_rows(db, instances)

    # 列 = 各实例「模板字段 ⊕ 动态字段」的并集，按模板里的出现顺序排列
    columns: list[tuple[str, str]] = []
    seen: set[str] = set()
    for instance in instances:
        schema = _schema_of(db, instance)
        for section in schema.sections:
            for field in section.fields:
                if field.key in seen:
                    continue
                seen.add(field.key)
                columns.append((field.key, field.label))
                for column in getattr(field, "columns", []) or []:
                    ref = f"{field.key}.{column.key}"
                    if ref in seen:
                        continue
                    seen.add(ref)
                    columns.append((ref, f"{field.label} · {column.label}"))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for _, label in META_COLUMNS] + [label for _, label in columns])

    for row in rows:
        values = row["values"]
        line = [row[key] for key, _ in META_COLUMNS]
        for key, _ in columns:
            line.append(_cell(values, key))
        writer.writerow(line)

    # BOM：Excel 靠它认出 UTF-8，否则中文列名全是乱码
    return "﻿" + buffer.getvalue()


def _cell(values: dict[str, Any], ref: str) -> str:
    """取一个字段的值。子表列（`items.amount`）展开成多行，便于在 Excel 里读。"""
    if "." not in ref:
        return _text(values.get(ref))

    table_key, column_key = ref.split(".", 1)
    rows = values.get(table_key)
    if not isinstance(rows, list):
        return ""
    parts = [
        _text(row.get(column_key))
        for row in rows
        if isinstance(row, dict) and row.get(column_key) not in (None, "", [])
    ]
    return " | ".join(parts)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (list, tuple)):
        return "、".join(_text(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}={_text(v)}" for k, v in value.items())
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
