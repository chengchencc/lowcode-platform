"""机制 C：运行中动态追加字段（PRD §3.4）。

场景：流程跑到一半，需要临时加一个字段（如「合同编号」）。

约束（PRD 明列，此处逐条落地）：
- 只作用于**该实例**，不入模板
- 追加后**不可物理删除**，只能停用/隐藏
- 实例归档后不可再追加
- 仅支持基础控件（文本/数字/日期/下拉/附件）—— 不支持子表与公式
- 默认**只读**，仅指定的目标节点可编辑；追加点之前的节点不可见

本模块负责两件事，都是纯函数：
`normalize_spec()` 校验追加请求；`merge_ext_fields()` 把动态字段并进模板 schema，
使渲染器不必区分「模板字段」与「扩展字段」。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core.constants import FieldType
from app.engine.errors import EngineError
from app.schemas.form_schema import FieldDef, FieldOption, FormSchema, SectionDef

#: 机制 C 允许的控件（PRD §3.4：文本/数字/日期/下拉/附件）
EXT_FIELD_TYPES: frozenset[str] = frozenset(
    {
        FieldType.TEXT,
        FieldType.TEXTAREA,
        FieldType.NUMBER,
        FieldType.DATE,
        FieldType.DATETIME,
        FieldType.SELECT,
        FieldType.ATTACHMENT,
    }
)

#: 需要配选项的控件
NEEDS_OPTIONS = frozenset({FieldType.SELECT})

#: 动态字段归入的虚拟分区（模板里没有对应分区时用）
VIRTUAL_SECTION_KEY = "sec_ext"
VIRTUAL_SECTION_TITLE = "扩展字段"

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


class ExtFieldError(EngineError):
    """追加字段的请求不合法。"""

    code = "EXT_FIELD_INVALID"


@dataclass(frozen=True, slots=True)
class ExtFieldSpec:
    """一次「追加字段」的请求。"""

    label: str
    type: str
    #: 可编辑的节点；不给则由服务层填「当前待办节点」
    editable_node_ids: tuple[str, ...] = ()
    required: bool = False
    section_key: str | None = None
    config: dict[str, Any] | None = None
    placeholder: str | None = None


def slugify(label: str) -> str:
    """把标签变成可用于 key 的片段。

    中文标签 slug 后会只剩空白，此时退化成 `field` —— key 的唯一性由序号保证，
    slug 只是让 key 可读一点。
    """
    slug = _SLUG_RE.sub("_", label.strip().lower()).strip("_")
    return slug[:24] or "field"


def make_field_key(seq: int, label: str) -> str:
    """`ext_{序号}_{slug}`。`ext_` 前缀保证不与模板字段冲突（PRD §3.4）。"""
    return f"ext_{seq}_{slugify(label)}"


def normalize_spec(spec: ExtFieldSpec) -> ExtFieldSpec:
    """校验并补齐追加请求。不合法时抛 `ExtFieldError`。"""
    label = (spec.label or "").strip()
    if not label:
        raise ExtFieldError("字段名称不能为空")

    if spec.type not in EXT_FIELD_TYPES:
        raise ExtFieldError(
            f"动态字段只支持基础控件（{'、'.join(sorted(EXT_FIELD_TYPES))}），"
            f"不支持 {spec.type}"
        )

    config = dict(spec.config or {})
    if spec.type in NEEDS_OPTIONS:
        options = config.get("options") or []
        if not options:
            raise ExtFieldError("下拉字段需要至少一个选项")

    if spec.required and spec.type == FieldType.ATTACHMENT:
        # 允许，但提醒一下——附件必填意味着处理人必须传文件才能过
        pass

    return ExtFieldSpec(
        label=label,
        type=spec.type,
        editable_node_ids=tuple(spec.editable_node_ids),
        required=bool(spec.required),
        section_key=spec.section_key,
        config=config,
        placeholder=spec.placeholder or config.get("placeholder"),
    )


def to_field_def(
    *,
    field_key: str,
    label: str,
    field_type: str,
    required: bool = False,
    config: dict[str, Any] | None = None,
    placeholder: str | None = None,
    sort: int = 0,
    disabled: bool = False,
) -> FieldDef:
    """把动态字段定义转成渲染器认识的 `FieldDef`。

    `visible_at_start=False`：动态字段是运行中追加的，发起阶段当然不该出现。
    """
    config = config or {}
    options = [
        FieldOption(label=str(o.get("label", "")), value=o.get("value"))
        for o in (config.get("options") or [])
    ]
    return FieldDef(
        key=field_key,
        label=label,
        type=field_type,
        sort=sort,
        required=required,
        placeholder=placeholder,
        default_value=config.get("defaultValue"),
        options=options,
        visible_at_start=False,
    )


def merge_ext_fields(
    form_schema: FormSchema,
    ext_fields: Sequence[Any],
) -> FormSchema:
    """把动态字段并进模板 schema，供渲染器统一处理。

    `ext_fields` 每项需有 `field_key / label / type / required / config /
    section_key / seq / status`（ORM 行或同形 dict 均可）。

    - 停用（status != ACTIVE）的字段**不并入** —— 界面上消失，但历史快照里仍有定义
    - 未指定 section_key 的归入虚拟分区「扩展字段」
    """
    active = sorted(
        (f for f in ext_fields if _attr(f, "status") == "ACTIVE"),
        key=lambda f: _attr(f, "seq") or 0,
    )
    if not active:
        return form_schema

    # 复制一份，别改到调用方传进来的 schema
    sections = [
        SectionDef(
            key=s.key,
            title=s.title,
            stage=s.stage,
            sort=s.sort,
            description=s.description,
            collapsible=s.collapsible,
            columns=s.columns,
            fields=list(s.fields),
        )
        for s in form_schema.sections
    ]
    by_key = {s.key: s for s in sections}

    virtual = SectionDef(
        key=VIRTUAL_SECTION_KEY,
        title=VIRTUAL_SECTION_TITLE,
        stage="supplement",
        # 排在最后：动态追加的字段不该插到申请区中间
        sort=(max((s.sort or 0 for s in sections), default=0) + 1),
        description="流程运行中追加的字段",
        fields=[],
    )

    for ext in active:
        field_key = _attr(ext, "field_key")
        section_key = _attr(ext, "section_key") or VIRTUAL_SECTION_KEY
        target = by_key.get(section_key)
        if target is None:
            # 模板里没有这个分区（或已被删）→ 落到虚拟分区
            if virtual.key not in by_key:
                sections.append(virtual)
                by_key[virtual.key] = virtual
            target = virtual

        target.fields.append(
            to_field_def(
                field_key=field_key,
                label=_attr(ext, "label") or field_key,
                field_type=_attr(ext, "type"),
                required=bool(_attr(ext, "required")),
                config=_attr(ext, "config") or {},
                placeholder=_attr(ext, "placeholder"),
                sort=_attr(ext, "seq") or 0,
            )
        )

    if virtual.key in by_key and not by_key[virtual.key].fields:
        sections = [s for s in sections if s.key != virtual.key]

    return FormSchema(
        model_version=form_schema.model_version,
        layout=form_schema.layout,
        sections=sections,
        rules=form_schema.rules,
        title_field=form_schema.title_field,
    )


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """同时支持 ORM 行与 dict。"""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)
