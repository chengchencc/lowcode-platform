"""字段权限矩阵求值（PRD §3.4 机制 A / 机制 B）。

这是「审批过程中表单字段逐步丰富」的核心：同一个字段在不同节点上
可以是隐藏 / 只读 / 可编辑，且**每次写入都累积进实例数据**。

求值顺序（**后者覆盖前者**）：

| 层 | 规则 | 说明 |
|---|---|---|
| L0 | 节点类型默认 | start：`visible_at_start ? editable : hidden`；审批/填写/抄送：`stage=='apply' ? readonly : hidden` |
| L1 | 分区批量 | `base` + `partitions[分区key]` —— 机制 B 的「按分区设模板」 |
| L2 | 单字段覆盖 | `overrides[字段key]` —— 机制 A 的「个别字段覆盖」 |
| L3 | 条件覆盖 | `conditional_overrides`，按声明序，命中即覆盖 |
| L4 | 硬约束 | 公式字段永远不可编辑；模板里 `required=true` 的字段在被设为可编辑时强制必填 |
| L5 | 扩展字段 | 机制 C（M5）：仅目标节点可编辑，之后只读，之前不可见 |

**覆盖是「后写胜」，允许 hidden → editable 的反向点亮** —— 这正是机制 B 的关键：
补充区的字段默认对所有节点隐藏，由某个节点显式打开。

返回值带 `reason`，便于前端提示与设计器冲突排查。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.constants import COMPUTED_FIELD_TYPES, DISPLAY_FIELD_TYPES, SectionStage
from app.engine.conditions import evaluate_group
from app.schemas.flow_definition import FieldPermissionRule, PermMode

#: 权限模式 → (visible, editable, required)
MODE_TABLE: dict[str, tuple[bool, bool, bool]] = {
    "hidden": (False, False, False),
    "readonly": (True, False, False),
    "editable": (True, True, False),
    "editable-required": (True, True, True),
}


@dataclass(frozen=True, slots=True)
class FieldPermission:
    visible: bool
    editable: bool
    required: bool
    #: 命中的层与来源，如 "L2:overrides[invoiceNo]=editable"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "visible": self.visible,
            "editable": self.editable,
            "required": self.required,
            "reason": self.reason,
        }


def _from_mode(mode: str, reason: str) -> FieldPermission:
    visible, editable, required = MODE_TABLE.get(mode, MODE_TABLE["readonly"])
    return FieldPermission(visible, editable, required, reason)


#: 子表列的引用记法（与 form_schema 的记法一致）
def column_ref(subtable_key: str, column_key: str) -> str:
    return f"{subtable_key}[].{column_key}"


def resolve_field_permissions(
    *,
    form_schema: Any,
    node_type: str,
    rule: FieldPermissionRule | None,
    values: Mapping[str, Any] | None = None,
) -> dict[str, FieldPermission]:
    """算出「在这个节点上，每个字段是什么权限」。

    `form_schema` 是 `schemas/form_schema.FormSchema`（不 import 其类型是为了
    避免 engine 反向依赖 schemas 的具体模块，运行时按属性访问即可）。
    """
    values = values or {}
    result: dict[str, FieldPermission] = {}

    for section in form_schema.sections:
        stage = getattr(section, "stage", SectionStage.APPLY)
        for field in section.fields:
            parent_perm = _resolve_one(
                field_key=field.key,
                field_type=field.type,
                section_key=section.key,
                section_stage=stage,
                schema_required=bool(getattr(field, "required", False)),
                visible_at_start=bool(getattr(field, "visible_at_start", True)),
                node_type=node_type,
                rule=rule,
                values=values,
            )
            result[field.key] = parent_perm

            for col in getattr(field, "columns", []) or []:
                ref = column_ref(field.key, col.key)
                # 列的起点是**子表本体的解析结果**，而不是重新走一遍 L0/L1。
                # 这样「overrides 里只写了 items」时列会跟着子表走，
                # 想单独控制某一列再写 `items[].列名` 即可。
                col_perm = _resolve_column(
                    parent=parent_perm,
                    reference=ref,
                    field_type=col.type,
                    schema_required=bool(getattr(col, "required", False)),
                    rule=rule,
                    values=values,
                )
                # 可见性跟随子表：看不见的表格谈不上看它的列
                result[ref] = FieldPermission(
                    visible=parent_perm.visible and col_perm.visible,
                    editable=col_perm.editable,
                    required=col_perm.required,
                    reason=col_perm.reason,
                )

    return result


def _resolve_column(
    *,
    parent: FieldPermission,
    reference: str,
    field_type: str,
    schema_required: bool,
    rule: FieldPermissionRule | None,
    values: Mapping[str, Any],
) -> FieldPermission:
    """子表列的权限：从子表的解析结果出发，只应用列级的覆盖。

    注意**不再用子表的 editable 去 AND 列** —— 它们语义不同：
    子表可编辑 = 能增删行；列可编辑 = 能改这一列的值。
    财务补充核销正是「表格本体只读、某一列可填」的场景。
    """
    perm = FieldPermission(parent.visible, parent.editable, parent.required,
                           "继承子表权限")

    if rule is None:
        return _apply_hard_constraints(perm, field_type, schema_required)

    # L2：列级单字段覆盖
    if reference in rule.overrides:
        perm = _from_mode(rule.overrides[reference], f"L2:overrides[{reference}]")

    # L3：列级条件覆盖
    for index, conditional in enumerate(rule.conditional_overrides):
        if conditional.field_key != reference:
            continue
        if evaluate_group(conditional.when, values):
            perm = _from_mode(conditional.mode, f"L3:conditional_overrides[{index}] 命中")
            break

    return _apply_hard_constraints(perm, field_type, schema_required)


def _resolve_one(
    *,
    field_key: str,
    field_type: str,
    section_key: str,
    section_stage: str,
    schema_required: bool,
    visible_at_start: bool,
    node_type: str,
    rule: FieldPermissionRule | None,
    values: Mapping[str, Any],
) -> FieldPermission:
    # ---- L0 节点类型默认 ----
    if node_type == "start":
        mode: PermMode = "editable" if visible_at_start else "hidden"
        perm = _from_mode(
            mode,
            "L0:start 阶段"
            + ("（字段标记为发起可见）" if visible_at_start else "（补充字段默认隐藏）"),
        )
    else:
        # 申请区在后续节点默认只读；其他区（审批区/补充区/归档区）默认隐藏，
        # 由节点显式打开 —— 这就是「财务补充字段申请人全程看不到」的默认保障
        mode = "readonly" if section_stage == SectionStage.APPLY else "hidden"
        perm = _from_mode(mode, f"L0:{node_type} 节点的分区默认（stage={section_stage}）")

    if rule is None:
        return _apply_hard_constraints(perm, field_type, schema_required)

    # ---- L1 分区批量 ----
    if section_key in rule.partitions:
        perm = _from_mode(rule.partitions[section_key], f"L1:partitions[{section_key}]")
    else:
        perm = _from_mode(rule.base, "L1:base")

    # ---- L2 单字段覆盖 ----
    if field_key in rule.overrides:
        perm = _from_mode(rule.overrides[field_key], f"L2:overrides[{field_key}]")

    # ---- L3 条件覆盖 ----
    for index, conditional in enumerate(rule.conditional_overrides):
        if conditional.field_key != field_key:
            continue
        if evaluate_group(conditional.when, values):
            perm = _from_mode(
                conditional.mode,
                f"L3:conditional_overrides[{index}] 命中",
            )
            break

    # ---- L4 硬约束 ----
    return _apply_hard_constraints(perm, field_type, schema_required)


def _apply_hard_constraints(
    perm: FieldPermission, field_type: str, schema_required: bool
) -> FieldPermission:
    """模板级的硬约束，不可被节点配置覆盖。"""
    if field_type in DISPLAY_FIELD_TYPES:
        # 展示控件只负责排版/说明，永远只读、谈不上必填
        return FieldPermission(
            visible=perm.visible,
            editable=False,
            required=False,
            reason=(perm.reason + " → 展示字段只读"),
        )

    if field_type in COMPUTED_FIELD_TYPES:
        # 公式字段的值由计算得出，永远只读、也谈不上必填
        return FieldPermission(
            visible=perm.visible,
            editable=False,
            required=False,
            reason=(perm.reason + " → L4:公式字段只读"),
        )

    if perm.editable and schema_required and not perm.required:
        return FieldPermission(
            perm.visible, perm.editable, True,
            reason=perm.reason + " → L4:模板标记必填",
        )
    return perm


def resolve_view_permissions(form_schema: Any) -> dict[str, FieldPermission]:
    """归档 / 抄送 / 非当前处理人的视角：全部可见、全部只读。

    支撑「申请人全程看不到补充字段，通过后归档可见」这条 PRD 验收点 ——
    实例进入终态后走这个函数而不是节点矩阵。
    """
    out: dict[str, FieldPermission] = {}
    for section in form_schema.sections:
        for field in section.fields:
            out[field.key] = FieldPermission(True, False, False, "归档视角：全量只读")
            for col in getattr(field, "columns", []) or []:
                out[column_ref(field.key, col.key)] = FieldPermission(
                    True, False, False, "归档视角：全量只读"
                )
    return out


def editable_keys(permissions: Mapping[str, FieldPermission]) -> set[str]:
    return {k for k, p in permissions.items() if p.editable}


def visible_keys(permissions: Mapping[str, FieldPermission]) -> set[str]:
    return {k for k, p in permissions.items() if p.visible}


# --------------------------------------------------------------------------- 机制 C（M5 占位）


@dataclass(frozen=True, slots=True)
class ExtFieldView:
    """实例级动态追加字段（PRD §3.4 机制 C）。

    M5 才会真正创建，这里先给出求值所需的形态，
    使 permissions 模块在 M5 无需改动调用点。
    """

    field_key: str
    label: str
    type: str
    required: bool = False
    #: 可编辑的节点
    editable_node_ids: Sequence[str] = ()
    #: 从哪个节点开始可见（之前不可见）
    visible_from_node_id: str | None = None
    active: bool = True


def apply_ext_fields(
    permissions: dict[str, FieldPermission],
    ext_fields: Sequence[ExtFieldView],
    *,
    node_id: str,
    node_ancestors: Sequence[str],
) -> dict[str, FieldPermission]:
    """把机制 C 的扩展字段叠加到权限表上（L5）。

    规则：追加点之前的节点不可见；可编辑节点内可编辑；其余节点只读。
    """
    for ext in ext_fields:
        if not ext.active:
            permissions.pop(ext.field_key, None)
            continue

        visible = True
        if ext.visible_from_node_id is not None:
            visible = ext.visible_from_node_id in set(node_ancestors)

        if not visible:
            permissions[ext.field_key] = FieldPermission(False, False, False, "L5:扩展字段尚未生效")
            continue

        editable = node_id in set(ext.editable_node_ids)
        permissions[ext.field_key] = FieldPermission(
            True,
            editable,
            editable and ext.required,
            f"L5:扩展字段（{'可编辑' if editable else '只读'}）",
        )
    return permissions


__all__ = [
    "ExtFieldView",
    "FieldPermission",
    "MODE_TABLE",
    "apply_ext_fields",
    "column_ref",
    "editable_keys",
    "resolve_field_permissions",
    "resolve_view_permissions",
    "visible_keys",
]
