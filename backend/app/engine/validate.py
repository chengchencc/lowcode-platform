"""流程定义校验器（PRD F2.7）。

职责：**保存/发布前做静态检查，非法定义不可发布**。

与 `compile.py` 的分工：
- `compile.py` 检查「结构能不能编译成可执行形态」（id 唯一、分支完整性…），
  失败即抛异常 —— 它面向引擎
- `validate.py` 检查「配置是否讲得通」（审批人配了吗、条件引用的字段还在吗…），
  收集全部问题一次性返回 —— 它面向设计器

因此 validate 会先调 compile，再把业务规则叠加上去。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.engine.compile import compile_flow
from app.engine.errors import FlowInvalid
from app.engine.types import CompiledFlow, NodeDef
from app.schemas.flow_definition import (
    ApprovalNode,
    AssigneeSource,
    CcNode,
    ConditionNode,
    FillNode,
    FlowDefinition,
    ParallelNode,
)

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    node_id: str | None = None
    #: 定位用的路径（如 `steps[0].branches[1]`），设计器据此高亮
    path: str = ""
    severity: Severity = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "node_id": self.node_id,
            "path": self.path,
            "severity": self.severity,
        }


@dataclass
class IssueCollector:
    issues: list[ValidationIssue] = field(default_factory=list)

    def error(self, code: str, message: str, *, node_id: str | None = None, path: str = "") -> None:
        self.issues.append(ValidationIssue(code, message, node_id, path, "error"))

    def warn(self, code: str, message: str, *, node_id: str | None = None, path: str = "") -> None:
        self.issues.append(ValidationIssue(code, message, node_id, path, "warning"))

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)


#: 表单里可以充当「人员」的控件类型
USER_FIELD_TYPES = {"user", "user_multi"}
DEPT_FIELD_TYPES = {"dept", "dept_multi"}


def _form_field_index(form_schema: Any) -> dict[str, str]:
    """{字段key: 控件类型}，含子表列的 `items[].amount` 记法。"""
    index: dict[str, str] = {}
    if form_schema is None:
        return index
    for section in getattr(form_schema, "sections", []):
        for f in section.fields:
            index[f.key] = f.type
            for col in getattr(f, "columns", []) or []:
                index[f"{f.key}[].{col.key}"] = col.type
    return index


def _referenced_fields_in_condition(node: Any, object: Any) -> list[str]:
    """递归取出条件组里引用的所有字段。"""
    out: list[str] = []
    if object is None:
        return out
    for item in getattr(object, "conditions", []) or []:
        field_name = getattr(item, "field", None)
        if field_name is not None:
            out.append(field_name)
        else:
            out.extend(_referenced_fields_in_condition(node, item))
    return out


def _check_assignee_sources(
    collector: IssueCollector,
    *,
    sources: list[AssigneeSource],
    node_id: str,
    node_name: str,
    path: str,
    fields: dict[str, str],
) -> None:
    if not sources:
        collector.error(
            "NO_ASSIGNEE",
            f"「{node_name}」没有配置审批人来源，运行时无人可派 —— 请至少添加一条来源",
            node_id=node_id,
            path=path,
        )
        return

    for index, source in enumerate(sources):
        where = f"{path}.sources[{index}]"
        if source.type == "user" and not source.user_ids:
            collector.error("ASSIGNEE_SOURCE_EMPTY", f"「{node_name}」的「指定人员」来源没有选人", node_id=node_id, path=where)
        elif source.type == "role" and not source.role_ids:
            collector.error("ASSIGNEE_SOURCE_EMPTY", f"「{node_name}」的「指定角色」来源没有选角色", node_id=node_id, path=where)
        elif source.type in {"form_user_field", "form_dept_field"}:
            if not source.field:
                collector.error(
                    "ASSIGNEE_SOURCE_EMPTY",
                    f"「{node_name}」的「表单字段」来源没有指定字段",
                    node_id=node_id,
                    path=where,
                )
                continue
            actual = fields.get(source.field)
            if actual is None:
                collector.error(
                    "ASSIGNEE_FIELD_MISSING",
                    f"「{node_name}」引用的表单字段 “{source.field}” 不存在（可能已被删除）",
                    node_id=node_id,
                    path=where,
                )
            elif source.type == "form_user_field" and actual not in USER_FIELD_TYPES:
                collector.error(
                    "ASSIGNEE_FIELD_TYPE",
                    f"「{node_name}」的人员来源引用了 “{source.field}”（{actual} 类型），"
                    "应为人员选择控件",
                    node_id=node_id,
                    path=where,
                )
            elif source.type == "form_dept_field" and actual not in DEPT_FIELD_TYPES:
                collector.error(
                    "ASSIGNEE_FIELD_TYPE",
                    f"「{node_name}」的部门来源引用了 “{source.field}”（{actual} 类型），"
                    "应为部门选择控件",
                    node_id=node_id,
                    path=where,
                )
        elif source.type == "dept_manager" and source.dept_field:
            actual = fields.get(source.dept_field)
            if actual is None:
                collector.error(
                    "ASSIGNEE_FIELD_MISSING",
                    f"「{node_name}」引用的部门字段 “{source.dept_field}” 不存在",
                    node_id=node_id,
                    path=where,
                )
            elif actual not in DEPT_FIELD_TYPES:
                collector.error(
                    "ASSIGNEE_FIELD_TYPE",
                    f"「{node_name}」的部门字段 “{source.dept_field}” 是 {actual} 类型，应为部门选择控件",
                    node_id=node_id,
                    path=where,
                )


def _check_permissions(
    collector: IssueCollector,
    node: NodeDef,
    fields: dict[str, str],
    index_fields: set[str],
) -> None:
    """字段权限矩阵引用的字段必须存在。"""
    raw = node.raw
    rule = getattr(raw, "fields_permission", None)
    if rule is None:
        return

    for key in rule.overrides:
        if key in index_fields:
            continue
        # 子表本体也要存在
        if key in fields:
            continue
        collector.error(
            "PERMISSION_FIELD_MISSING",
            f"「{node.name}」的字段权限引用了不存在的字段 “{key}”（可能已被删除）",
            node_id=node.id,
            path=f"{node.id}.fields_permission.overrides",
        )

    for i, conditional in enumerate(rule.conditional_overrides):
        if conditional.field_key not in index_fields and conditional.field_key not in fields:
            collector.error(
                "PERMISSION_FIELD_MISSING",
                f"「{node.name}」的条件权限引用了不存在的字段 “{conditional.field_key}”",
                node_id=node.id,
                path=f"{node.id}.fields_permission.conditional_overrides[{i}]",
            )
        for ref in _referenced_fields_in_condition(node, conditional.when):
            if ref not in index_fields and ref not in fields:
                collector.error(
                    "CONDITION_FIELD_MISSING",
                    f"「{node.name}」的条件权限引用了不存在的字段 “{ref}”",
                    node_id=node.id,
                    path=f"{node.id}.fields_permission.conditional_overrides[{i}].when",
                )


def _check_condition_node(
    collector: IssueCollector,
    node: ConditionNode,
    fields: dict[str, str],
    index_fields: set[str],
) -> None:
    has_else = False
    for index, branch in enumerate(node.branches):
        base = f"{node.id}.branches[{index}]"
        if branch.when is None:
            has_else = True
            continue
        for ref in _referenced_fields_in_condition(node, branch.when):
            if ref not in index_fields and ref not in fields:
                collector.error(
                    "CONDITION_FIELD_MISSING",
                    f"分支「{branch.name or branch.id}」引用了不存在的字段 “{ref}”（可能已被删除）",
                    node_id=node.id,
                    path=f"{base}.when",
                )

    if not has_else:
        collector.warn(
            "NO_ELSE_BRANCH",
            f"条件节点「{node.name}」没有「否则」分支；当所有条件都不满足时，"
            "流程会直接跳过该节点继续往下走",
            node_id=node.id,
            path=node.id,
        )


def validate_flow_definition(
    definition: FlowDefinition,
    form_schema: Any = None,
) -> list[ValidationIssue]:
    """校验流程定义。返回全部问题（error 阻断发布，warning 只提示）。"""
    collector = IssueCollector()

    # 1) 先过结构关：结构不合法就没必要继续查业务规则
    try:
        compiled = compile_flow(definition)
    except FlowInvalid as exc:
        collector.error("FLOW_INVALID", str(exc), node_id=exc.node_id)
        return collector.issues

    if not compiled.root_list:
        collector.warn(
            "NO_STEP",
            "流程没有任何步骤；提交后会直接结束为「已通过」，通常不是你想要的",
            path="steps",
        )

    fields = _form_field_index(form_schema)
    index_fields = set(fields)

    # 2) 逐节点查业务规则
    for node in compiled.nodes.values():
        if node.type in {"start", "end"}:
            continue

        path = node.id
        if node.type in {"approval", "fill"}:
            assert isinstance(node.raw, (ApprovalNode, FillNode))
            _check_assignee_sources(
                collector,
                sources=node.raw.assignee.sources,
                node_id=node.id,
                node_name=node.name,
                path=path,
                fields=fields,
            )
            if (
                node.raw.assignee.mode == "SINGLE"
                and any(s.type == "initiator_select" for s in node.raw.assignee.sources)
                and node.raw.assignee.initiator_select is None
            ):
                collector.error(
                    "INITIATOR_SELECT_SCOPE",
                    f"「{node.name}」需要发起人指定审批人，但没有配置候选范围",
                    node_id=node.id,
                    path=path,
                )
            _check_permissions(collector, node, fields, index_fields)

        elif node.type == "parallel":
            assert isinstance(node.raw, ParallelNode)
            if len(node.raw.members) == 1 and node.raw.mode == "any":
                collector.warn(
                    "SINGLE_MEMBER_ANY",
                    f"并行组「{node.name}」只有 1 个成员却用「或签」，等价于普通审批节点",
                    node_id=node.id,
                    path=path,
                )

        elif node.type == "condition":
            assert isinstance(node.raw, ConditionNode)
            _check_condition_node(collector, node.raw, fields, index_fields)

        elif node.type == "cc":
            assert isinstance(node.raw, CcNode)
            if not node.raw.cc_to.sources:
                collector.warn(
                    "CC_NO_TARGET",
                    f"抄送节点「{node.name}」没有配置抄送对象，不会通知任何人",
                    node_id=node.id,
                    path=path,
                )
            _check_assignee_sources_soft(collector, node.raw, fields)

    # 3) 退回目标合法性
    _check_return_targets(collector, compiled)

    # 4) 重复节点名
    _check_duplicate_names(collector, compiled)

    return collector.issues


def _check_assignee_sources_soft(
    collector: IssueCollector, node: CcNode, fields: dict[str, str]
) -> None:
    """抄送对象的来源检查 —— 比审批宽松：未命中不算错，但引用不存在的字段仍是错。"""
    from app.schemas.flow_definition import AssigneeRule

    rule: AssigneeRule = node.cc_to
    for index, source in enumerate(rule.sources):
        where = f"{node.id}.cc_to.sources[{index}]"
        if (
            source.type in {"form_user_field", "form_dept_field"}
            and source.field
            and source.field not in fields
        ):
            collector.error(
                "CC_FIELD_MISSING",
                f"抄送节点「{node.name}」引用的表单字段 “{source.field}” 不存在",
                node_id=node.id,
                path=where,
            )


def _check_return_targets(collector: IssueCollector, compiled: CompiledFlow) -> None:
    """退回目标必须是该节点**前序**存在的审批/填写节点。"""
    from app.engine.types import Cursor

    for node in compiled.nodes.values():
        configured = getattr(node.raw, "return_targets", None)
        if configured is None or not configured:
            continue

        # 用该节点所在的第一个位置来计算前序集合
        cursor = Cursor(node.id, node.gates)
        candidates = {c.id for c in compiled.return_target_candidates(cursor)}
        for target in configured:
            if target not in compiled.nodes:
                collector.error(
                    "RETURN_TARGET_MISSING",
                    f"「{node.name}」的退回目标 “{target}” 不存在",
                    node_id=node.id,
                    path=f"{node.id}.return_targets",
                )
            elif target not in candidates:
                collector.error(
                    "RETURN_TARGET_NOT_ANCESTOR",
                    f"「{node.name}」的退回目标 “{target}” 不是它的前序审批/填写节点，"
                    "退回后无法到达",
                    node_id=node.id,
                    path=f"{node.id}.return_targets",
                )


def _check_duplicate_names(collector: IssueCollector, compiled: CompiledFlow) -> None:
    seen: dict[str, str] = {}
    for node in compiled.nodes.values():
        if node.type in {"start", "end"}:
            continue
        if node.name in seen:
            collector.warn(
                "DUPLICATE_NODE_NAME",
                f"节点名「{node.name}」重复（同时出现在 {seen[node.name]} 与 {node.id}），"
                "审批人容易分不清",
                node_id=node.id,
                path=node.id,
            )
        else:
            seen[node.name] = node.id


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(i.severity == "error" for i in issues)
