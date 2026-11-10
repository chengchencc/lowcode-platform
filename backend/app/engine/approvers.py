"""审批人解析（PRD §3.3.2「动态审批人」）。

**引擎不直接查数据库**：所有查询通过 `ApproverProvider` 协议注入，
实现放在 services 层。这样解析逻辑（合并、去重、未命中兜底）可以纯函数测试。

解析**时机**：任务进入该节点时实时解析并快照写入任务 —— 组织调整不影响已生成的任务。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.schemas.flow_definition import AssigneeRule, AssigneeSource


class ApproverProvider(Protocol):
    """解析审批人所需的数据访问。由 services 层实现。"""

    def users_by_ids(self, user_ids: Sequence[int]) -> list[int]:
        """按 id 取**启用中**的用户。"""

    def users_by_role(self, role_ids: Sequence[int]) -> list[int]:
        """取持有任一角色的启用用户。"""

    def dept_manager(self, dept_id: int) -> list[int]:
        """部门主管（PRD §3.3.2：V1 用部门主管近似直属上级）。"""

    def active_user_ids(self, user_ids: Sequence[int]) -> list[int]:
        """过滤出启用中的用户（表单人员字段可能选到已停用的人）。"""

    def admin_user_ids(self) -> list[int]:
        """平台管理员 —— 未命中审批人时的兜底。"""

    def current_active_users(self) -> list[int]:
        """全部启用用户（指定人员来源的合法化校验用）。"""


@dataclass(frozen=True, slots=True)
class ApproverContext:
    """解析所需的运行时上下文。"""

    initiator_id: int
    initiator_dept_id: int | None = None
    values: Mapping[str, Any] = field(default_factory=dict)
    #: {节点id: [该节点已同意的处理人]}，供 prev_node_actors 来源使用
    prev_actors: Mapping[str, Sequence[int]] = field(default_factory=dict)
    #: 上一个完成节点的 id（prev_node_actors 未指定 node_id 时的默认目标）
    last_completed_node_id: str | None = None
    #: 发起节点 id —— prev_node_actors 指向它时解析为发起人
    start_node_id: str | None = None
    #: 发布时校验过「无审批人」的节点：这些节点即使未命中也不算异常
    #: （on_empty="block_publish" 的节点在发布阶段就该被拦下）
    strict_on_empty: bool = False


@dataclass
class Resolution:
    """解析结果。"""

    user_ids: list[int] = field(default_factory=list)
    #: 每个来源分别贡献了谁，写入任务的 approver_resolved 快照，便于追溯
    by_source: list[dict[str, Any]] = field(default_factory=list)
    #: 未命中任何审批人 → 转管理员并标记异常（PRD §3.3.2，不静默通过）
    abnormal: bool = False
    reason: str | None = None
    fallback_admin_ids: list[int] = field(default_factory=list)

    @property
    def resolved_ids(self) -> list[int]:
        """最终写入任务的处理人（含兜底管理员）。"""
        if self.abnormal:
            return list(dict.fromkeys([*self.user_ids, *self.fallback_admin_ids]))
        return list(self.user_ids)


def _form_ids(values: Mapping[str, Any], key: str | None) -> list[int]:
    """从表单值里取出人员/部门 id（控件可能是单值或多值）。"""
    if not key:
        return []
    raw = values.get(key)
    if raw is None or raw == "":
        return []
    items = raw if isinstance(raw, (list, tuple, set)) else [raw]
    out: list[int] = []
    for item in items:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def resolve_source(
    source: AssigneeSource,
    ctx: ApproverContext,
    provider: ApproverProvider,
) -> tuple[list[int], str]:
    """解析单个来源，返回 (用户id列表, 说明)。"""
    if source.type == "user":
        ids = provider.users_by_ids(source.user_ids)
        return ids, f"指定人员 {len(source.user_ids)} 人"

    if source.type == "role":
        ids = provider.users_by_role(source.role_ids)
        return ids, f"角色 {len(source.role_ids)} 个"

    if source.type == "dept_manager":
        # 固定的部门优先；其次是表单里指定的部门字段；都没有则用发起人所在部门
        if source.dept_ids:
            dept_ids = list(source.dept_ids)
        elif source.dept_field:
            dept_ids = _form_ids(ctx.values, source.dept_field)
        else:
            dept_ids = [ctx.initiator_dept_id] if ctx.initiator_dept_id else []
        collected: list[int] = []
        for dept_id in dept_ids:
            collected.extend(provider.dept_manager(dept_id))
        return list(dict.fromkeys(collected)), f"部门主管（{len(dept_ids)} 个部门）"

    if source.type == "form_user_field":
        picked = _form_ids(ctx.values, source.field)
        ids = provider.active_user_ids(picked)
        return ids, f"表单人员字段 {source.field}"

    if source.type == "form_dept_field":
        dept_ids = _form_ids(ctx.values, source.field)
        collected: list[int] = []
        for dept_id in dept_ids:
            collected.extend(provider.dept_manager(dept_id))
        return list(dict.fromkeys(collected)), f"表单部门字段 {source.field} 的负责人"

    if source.type == "initiator_select":
        # 发起人在提交时选的人，已落在表单值里（字段名由提交端约定）
        picked = _form_ids(ctx.values, "__initiator_select__")
        ids = provider.active_user_ids(picked)
        return ids, "发起人指定"

    if source.type == "prev_node_actors":
        node_id = source.node_id or ctx.last_completed_node_id
        # 上一节点就是发起节点（首个审批节点的默认情况）：处理人即发起人
        if not node_id or node_id == ctx.start_node_id:
            return [ctx.initiator_id], "发起人（上一节点）"
        actors = list(ctx.prev_actors.get(node_id, ()))
        ids = provider.active_user_ids(actors)
        return ids, f"节点 {node_id} 的处理人"

    return [], f"未知来源 {source.type}"


def _resolves_to_initiator(source: AssigneeSource, ctx: ApproverContext) -> bool:
    """该来源是否明确取到了发起节点（上一节点=发起人）。"""
    if source.type != "prev_node_actors":
        return False
    node_id = source.node_id or ctx.last_completed_node_id
    return not node_id or node_id == ctx.start_node_id


def resolve_approvers(
    rule: AssigneeRule,
    ctx: ApproverContext,
    provider: ApproverProvider,
) -> Resolution:
    """解析一个节点的审批人。

    多条来源的结果**合并去重**（PRD §3.3.2「支持组合」）。
    未命中任何审批人时：按 `on_empty` 转管理员并标记异常，**不静默通过**。
    """
    result = Resolution()
    seen: dict[int, None] = {}

    for source in rule.sources:
        ids, description = resolve_source(source, ctx, provider)
        # 发起人自己不做自己的审批人（避免自审）；
        # 但「上一节点处理人」明确选了发起节点，是设计者的有意配置，允许自审。
        if _resolves_to_initiator(source, ctx):
            filtered = list(ids)
        else:
            filtered = [uid for uid in ids if uid != ctx.initiator_id]
        result.by_source.append({"type": source.type, "desc": description, "user_ids": filtered})
        for uid in filtered:
            seen.setdefault(uid, None)

    result.user_ids = list(seen)

    if not result.user_ids:
        admins = provider.admin_user_ids()
        result.abnormal = True
        result.fallback_admin_ids = admins
        result.reason = (
            "未解析到任何审批人，已转交平台管理员"
            if admins
            else "未解析到任何审批人，且系统没有可用的平台管理员"
        )

    return result


def resolve_cc(
    rule: AssigneeRule,
    ctx: ApproverContext,
    provider: ApproverProvider,
) -> Resolution:
    """抄送对象的解析。抄送未命中**不算异常**（不阻塞主线，也不该打扰管理员）。"""
    result = Resolution()
    for source in rule.sources:
        ids, description = resolve_source(source, ctx, provider)
        result.by_source.append({"type": source.type, "desc": description, "user_ids": ids})
        for uid in ids:
            if uid not in result.user_ids:
                result.user_ids.append(uid)
    return result


def order_by_mode(mode: str, user_ids: Iterable[int]) -> list[int]:
    """按审批人模式决定初始顺序。

    - SEQUENTIAL：保持解析顺序（依次审批）
    - ALL / ANY：顺序不参与语义，但保持稳定便于断言与展示
    - SINGLE：只取第一个
    """
    ordered = list(dict.fromkeys(user_ids))
    if mode == "SINGLE":
        return ordered[:1]
    return ordered


def initial_status_for_mode(mode: str, index: int) -> str:
    """依次审批时只有第一个是待办，其余等待；其余模式全部同时待办。"""
    if mode == "SEQUENTIAL" and index > 0:
        return "WAITING"
    return "PENDING"
