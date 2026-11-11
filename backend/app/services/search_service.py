"""实例业务字段检索（M13）。

JSON 仍是业务数据唯一事实源；`instance_field_values` 是可重建的派生索引。
本模块负责：可检索字段配置、提交/审批时同步索引、筛选条件解析与 SQL 构造。
"""

from __future__ import annotations

import json
import operator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    DISPLAY_FIELD_TYPES,
    FieldType,
    FormulaType,
    InstanceStatus,
    SectionStage,
)
from app.core.errors import NotFoundError, UnprocessableError
from app.models import (
    FlowInstance,
    FormSearchField,
    FormTemplate,
    FormVersion,
    InstanceFieldValue,
)
from app.schemas.form_schema import FieldDef, FormSchema, parse_form_schema

MAX_FIELDS = 20
MAX_FILTERS = 10

TEXT_KINDS = {"text", "option", "date", "time", "datetime"}
NUMBER_KINDS = {"number", "bool", "user", "dept"}
MULTI_KINDS = {"multi_option", "user_multi", "dept_multi"}


@dataclass(frozen=True)
class SearchFilter:
    field: str
    kind: str
    op: str
    value: Any = None


# --------------------------------------------------------------------------- 字段元信息


def _filter_kind(field: FieldDef) -> str | None:
    if field.type in DISPLAY_FIELD_TYPES:
        return None
    if field.type in {FieldType.ATTACHMENT, FieldType.IMAGE, FieldType.SUBTABLE}:
        return None
    if field.type in {FieldType.TEXT, FieldType.TEXTAREA}:
        return "text"
    if field.type == FieldType.NUMBER:
        return "number"
    if field.type == FieldType.DATE:
        return "date"
    if field.type == FieldType.TIME:
        return "time"
    if field.type == FieldType.DATETIME:
        return "datetime"
    if field.type == FieldType.SWITCH:
        return "bool"
    if field.type in {FieldType.RADIO, FieldType.SELECT}:
        return "option"
    if field.type == FieldType.CHECKBOX:
        return "multi_option"
    if field.type == FieldType.USER:
        return "user"
    if field.type == FieldType.USER_MULTI:
        return "user_multi"
    if field.type == FieldType.DEPT:
        return "dept"
    if field.type == FieldType.DEPT_MULTI:
        return "dept_multi"
    if field.type == FieldType.CASCADER:
        return "multi_option"
    if field.type == FieldType.FORMULA and field.formula is not None:
        if field.formula.type == FormulaType.CONCAT:
            return "text"
        return "number"
    return None


def _field_options(field: FieldDef) -> list[Any]:
    values: list[Any] = []
    if field.type == FieldType.CASCADER and field.cascader is not None:
        for options in field.cascader.options_by_parent.values():
            values.extend(option.value for option in options)
    else:
        values.extend(option.value for option in field.options)
    # 去重且保持顺序
    seen: set[str] = set()
    out: list[Any] = []
    for value in values:
        marker = str(value)
        if marker not in seen:
            seen.add(marker)
            out.append(value)
    return out


def _latest_version(db: Session, template_id: int) -> FormVersion | None:
    return db.scalar(
        select(FormVersion)
        .where(FormVersion.template_id == template_id)
        .order_by(FormVersion.version_no.desc())
        .limit(1)
    )


def _schema_fields(schema: FormSchema) -> dict[str, tuple[FieldDef, bool]]:
    """顶层字段 → (字段定义, 发起阶段是否可见)。"""
    out: dict[str, tuple[FieldDef, bool]] = {}
    for section in schema.sections:
        for field in section.fields:
            if _filter_kind(field) is None:
                continue
            start_visible = field.visible_at_start and section.stage != SectionStage.SUPPLEMENT
            out[field.key] = (field, start_visible)
    return out


def configurable_fields(schema: FormSchema) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for field, start_visible in _schema_fields(schema).values():
        kind = _filter_kind(field)
        if kind is None:
            continue
        out.append({
            "field_key": field.key,
            "label": field.label,
            "field_type": str(field.type),
            "filter_kind": kind,
            "options": _field_options(field),
            "start_visible": start_visible,
        })
    return out


def _load_configs(db: Session, template_id: int) -> list[FormSearchField]:
    return list(
        db.scalars(
            select(FormSearchField)
            .where(FormSearchField.form_template_id == template_id)
            .order_by(FormSearchField.sort, FormSearchField.id)
        ).all()
    )


def list_search_fields(
    db: Session, template: FormTemplate, *, include_unselected: bool = True
) -> list[dict[str, Any]]:
    version = _latest_version(db, template.id)
    if version is None:
        return []
    schema = parse_form_schema(version.schema)
    available = {item["field_key"]: item for item in configurable_fields(schema)}
    configs = {item.field_key: item for item in _load_configs(db, template.id)}

    out: list[dict[str, Any]] = []
    for key, item in available.items():
        config = configs.get(key)
        out.append({
            **item,
            "selected": config is not None,
            "indexed_at": config.indexed_at.isoformat() if config and config.indexed_at else None,
        })
    if include_unselected:
        for key, config in configs.items():
            if key in available:
                continue
            out.append({
                "field_key": key,
                "label": config.label,
                "field_type": config.field_type,
                "filter_kind": config.filter_kind,
                "options": config.options or [],
                "start_visible": config.start_visible,
                "selected": True,
                "indexed_at": config.indexed_at.isoformat() if config.indexed_at else None,
            })
    return out


def save_search_fields(
    db: Session,
    template: FormTemplate,
    field_keys: list[str],
    *,
    actor_id: int,
) -> dict[str, Any]:
    if len(field_keys) > MAX_FIELDS:
        raise UnprocessableError(
            f"每个表单最多配置 {MAX_FIELDS} 个可检索字段", code="SEARCH_FIELD_LIMIT"
        )
    if len(set(field_keys)) != len(field_keys):
        raise UnprocessableError("可检索字段重复", code="SEARCH_FIELD_DUPLICATE")

    version = _latest_version(db, template.id)
    if version is None:
        raise NotFoundError("表单没有版本", code="FORM_VERSION_MISSING")
    available = {item["field_key"]: item for item in configurable_fields(parse_form_schema(version.schema))}

    missing = [key for key in field_keys if key not in available]
    if missing:
        raise UnprocessableError(
            f"字段不存在或不可检索：{', '.join(missing)}", code="SEARCH_FIELD_UNKNOWN"
        )

    existing = {item.field_key: item for item in _load_configs(db, template.id)}
    added = 0
    removed = 0
    for key, item in available.items():
        if key not in field_keys:
            continue
        config = existing.get(key)
        if config is None:
            config = FormSearchField(
                form_template_id=template.id,
                field_key=key,
                field_type=item["field_type"],
                filter_kind=item["filter_kind"],
                label=item["label"],
                options=item["options"] or None,
                start_visible=item["start_visible"],
                sort=field_keys.index(key),
                created_by=actor_id,
            )
            db.add(config)
            added += 1
        else:
            config.field_type = item["field_type"]
            config.filter_kind = item["filter_kind"]
            config.label = item["label"]
            config.options = item["options"] or None
            config.start_visible = item["start_visible"]
            config.sort = field_keys.index(key)

    for key, config in existing.items():
        if key in field_keys:
            continue
        db.delete(config)
        # 只清理本模板实例的索引；不同模板可能复用同名 field key
        instance_ids = select(FlowInstance.id).where(
            FlowInstance.flow_template_id == template.id
        )
        db.execute(
            InstanceFieldValue.__table__.delete().where(
                InstanceFieldValue.instance_id.in_(instance_ids),
                InstanceFieldValue.field_key == key,
            )
        )
        removed += 1

    db.commit()
    return {"added": added, "removed": removed, "needs_backfill": added > 0}


def assert_publish_consistency(db: Session, template_id: int, schema: FormSchema) -> None:
    """发布前校验：同一 field key 在各版本的类型必须一致。"""
    available = {
        item["field_key"]: item for item in configurable_fields(schema)
    }
    for config in _load_configs(db, template_id):
        item = available.get(config.field_key)
        if item is None:
            continue
        if item["filter_kind"] != config.filter_kind:
            raise UnprocessableError(
                f"字段「{config.label}」的可检索类型在版本间发生变化"
                f"（{config.filter_kind} → {item['filter_kind']}），"
                "请先在检索字段配置中移除它",
                code="SEARCH_FIELD_TYPE_CONFLICT",
            )
        config.label = item["label"]
        config.options = item["options"] or None
        config.start_visible = item["start_visible"]


def copy_configs(db: Session, source_template_id: int, target_template_id: int, actor_id: int) -> None:
    for config in _load_configs(db, source_template_id):
        db.add(
            FormSearchField(
                form_template_id=target_template_id,
                field_key=config.field_key,
                field_type=config.field_type,
                filter_kind=config.filter_kind,
                label=config.label,
                options=config.options,
                start_visible=config.start_visible,
                sort=config.sort,
                created_by=actor_id,
            )
        )


# --------------------------------------------------------------------------- 索引同步


def _empty_row(instance_id: int, field_key: str) -> InstanceFieldValue:
    return InstanceFieldValue(
        instance_id=instance_id, field_key=field_key, value_kind="empty", value_index=0
    )


def _rows_for(instance_id: int, config: FormSearchField, value: Any) -> list[InstanceFieldValue]:
    kind = config.filter_kind
    field_key = config.field_key
    if value is None or value == "" or value == []:
        return [_empty_row(instance_id, field_key)]

    def make(value_kind: str, *, text: str | None = None, num: float | None = None, index: int = 0):
        return InstanceFieldValue(
            instance_id=instance_id,
            field_key=field_key,
            value_kind=value_kind,
            value_text=text[:512] if text else text,
            value_num=num,
            value_index=index,
        )

    if kind in {"text", "option", "date", "time", "datetime"}:
        return [make("text", text=str(value).casefold())]
    if kind == "number":
        try:
            return [make("number", num=float(value))]
        except (TypeError, ValueError):
            return [_empty_row(instance_id, field_key)]
    if kind == "bool":
        return [make("bool", num=1.0 if value else 0.0)]
    if kind in {"user", "dept"}:
        try:
            return [make("id", num=float(value))]
        except (TypeError, ValueError):
            return [_empty_row(instance_id, field_key)]
    if kind in MULTI_KINDS:
        values = value if isinstance(value, (list, tuple)) else [value]
        rows = []
        for index, item in enumerate(values):
            if item in (None, ""):
                continue
            if kind == "multi_option":
                rows.append(make("text", text=str(item).casefold(), index=index))
            else:
                try:
                    rows.append(make("id", num=float(item), index=index))
                except (TypeError, ValueError):
                    continue
        return rows or [_empty_row(instance_id, field_key)]
    return [_empty_row(instance_id, field_key)]


def sync_instance_index(
    db: Session,
    *,
    instance,
    form_schema: FormSchema | None = None,
    configs: list[FormSearchField] | None = None,
) -> None:
    """在提交/审批的同一事务内重建该实例的索引；草稿不索引。"""
    db.execute(
        InstanceFieldValue.__table__.delete().where(
            InstanceFieldValue.instance_id == instance.id
        )
    )
    if instance.status == InstanceStatus.DRAFT:
        return
    configs = configs if configs is not None else _load_configs(db, instance.flow_template_id)
    if not configs:
        return
    values = instance.current_data or {}
    for config in configs:
        db.add_all(_rows_for(instance.id, config, values.get(config.field_key)))
    db.flush()


# --------------------------------------------------------------------------- 筛选


def allowed_fields(
    db: Session, template_id: int, *, start_only: bool
) -> dict[str, FormSearchField]:
    configs = _load_configs(db, template_id)
    if start_only:
        configs = [config for config in configs if config.start_visible]
    return {config.field_key: config for config in configs}


def parse_filters(raw: str | None, configs: dict[str, FormSearchField]) -> list[SearchFilter]:
    if not raw:
        return []
    if len(raw) > 8192:
        raise UnprocessableError("筛选条件过长", code="FILTER_INVALID")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UnprocessableError("筛选条件不是合法 JSON", code="FILTER_INVALID") from exc
    if not isinstance(payload, list) or len(payload) > MAX_FILTERS:
        raise UnprocessableError(
            f"筛选条件必须是数组且不超过 {MAX_FILTERS} 条", code="FILTER_INVALID"
        )

    out: list[SearchFilter] = []
    for item in payload:
        if not isinstance(item, dict):
            raise UnprocessableError("筛选条件格式错误", code="FILTER_INVALID")
        field_key = item.get("field")
        config = configs.get(str(field_key))
        if config is None:
            raise UnprocessableError(
                f"字段不可筛选：{field_key}", code="FILTER_FIELD_NOT_ALLOWED"
            )
        op = str(item.get("op") or "")
        value = item.get("value")
        _assert_filter(config.filter_kind, op, value)
        out.append(SearchFilter(field=config.field_key, kind=config.filter_kind, op=op, value=value))
    return out


def _assert_filter(kind: str, op: str, value: Any) -> None:
    allowed: set[str]
    if kind in {"text", "option", "date", "time", "datetime"}:
        allowed = {"eq", "in", "contains", "is_empty", "is_not_empty"}
        if kind in {"date", "time", "datetime"}:
            allowed |= {"gt", "gte", "lt", "lte", "between"}
    elif kind == "number":
        allowed = {"eq", "gt", "gte", "lt", "lte", "between", "is_empty", "is_not_empty"}
    elif kind == "bool":
        allowed = {"eq", "is_empty", "is_not_empty"}
    elif kind in {"multi_option", "user_multi", "dept_multi"}:
        allowed = {"has_any", "has_all", "is_empty", "is_not_empty"}
    elif kind in {"user", "dept"}:
        allowed = {"eq", "in", "is_empty", "is_not_empty"}
    else:
        raise UnprocessableError("字段类型不可筛选", code="FILTER_INVALID")

    if op not in allowed:
        raise UnprocessableError(f"操作符 {op} 不适用于该字段", code="FILTER_OP_INVALID")
    if op in {"is_empty", "is_not_empty"}:
        return
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise UnprocessableError("between 需要两个值", code="FILTER_VALUE_INVALID")
        return
    if op in {"in", "has_any", "has_all"}:
        if not isinstance(value, list) or not value:
            raise UnprocessableError("该操作符需要一个非空数组", code="FILTER_VALUE_INVALID")
        if len(value) > 50:
            raise UnprocessableError("筛选值过多", code="FILTER_VALUE_INVALID")
        return
    if value is None:
        raise UnprocessableError("筛选值不能为空", code="FILTER_VALUE_INVALID")


def _exists(*conditions) -> Any:
    sub = select(InstanceFieldValue.id).where(
        InstanceFieldValue.instance_id == FlowInstance.id, *conditions
    )
    return sub.exists()


def _apply(stmt: Select, flt: SearchFilter) -> Select:
    field = InstanceFieldValue.field_key == flt.field
    if flt.op == "is_empty":
        return stmt.where(_exists(field, InstanceFieldValue.value_kind == "empty"))
    if flt.op == "is_not_empty":
        return stmt.where(_exists(field, InstanceFieldValue.value_kind != "empty"))

    if flt.kind in {"text", "option", "date", "time", "datetime"}:
        value = str(flt.value).casefold()
        if flt.op == "contains":
            return stmt.where(
                _exists(field, InstanceFieldValue.value_text.contains(value, autoescape=True))
            )
        if flt.op == "in":
            values = [str(item).casefold() for item in flt.value]
            return stmt.where(_exists(field, InstanceFieldValue.value_text.in_(values)))
        if flt.op == "between":
            low, high = [str(item) for item in flt.value]
            return stmt.where(_exists(field, InstanceFieldValue.value_text.between(low, high)))
        comparisons = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
        if flt.op in comparisons:
            return stmt.where(
                _exists(field, comparisons[flt.op](InstanceFieldValue.value_text, value))
            )
        return stmt.where(_exists(field, InstanceFieldValue.value_text == value))

    if flt.kind in {"number", "bool", "user", "dept"}:
        if flt.op == "in":
            values = [float(item) for item in flt.value]
            return stmt.where(_exists(field, InstanceFieldValue.value_num.in_(values)))
        if flt.op == "between":
            low, high = [float(item) for item in flt.value]
            return stmt.where(_exists(field, InstanceFieldValue.value_num.between(low, high)))
        value = float(flt.value)
        if flt.op == "eq":
            return stmt.where(_exists(field, InstanceFieldValue.value_num == value))
        comparisons = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
        if flt.op in comparisons:
            return stmt.where(
                _exists(field, comparisons[flt.op](InstanceFieldValue.value_num, value))
            )

    if flt.kind in MULTI_KINDS:
        is_text = flt.kind == "multi_option"
        column = InstanceFieldValue.value_text if is_text else InstanceFieldValue.value_num
        values = [str(item).casefold() if is_text else float(item) for item in flt.value]
        if flt.op == "has_any":
            return stmt.where(_exists(field, column.in_(values)))
        if flt.op == "has_all":
            sub = (
                select(InstanceFieldValue.instance_id)
                .where(field, column.in_(values))
                .group_by(InstanceFieldValue.instance_id)
                .having(func.count(func.distinct(column)) == len(values))
            )
            return stmt.where(FlowInstance.id.in_(sub))

    raise UnprocessableError("筛选条件无法应用", code="FILTER_INVALID")


def apply_filters(stmt: Select, filters: list[SearchFilter]) -> Select:
    for flt in filters:
        stmt = _apply(stmt, flt)
    return stmt


def mark_backfilled(db: Session, template_id: int) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    for config in _load_configs(db, template_id):
        config.indexed_at = now
    db.commit()
