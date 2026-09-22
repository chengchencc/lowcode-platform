"""引擎的纯数据类型。

本模块**不得** import `app.db` / `app.models` —— 纯核心要能脱离数据库做单测
（TECH-DESIGN §2 的分层约束）。因此这里出现的都是 dataclass / 枚举，
不带任何 ORM 依赖。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.schemas.flow_definition import (
    ApprovalNode,
    Branch,
    CcNode,
    ConditionNode,
    EndNode,
    FillNode,
    FlowDefinition,
    NodeBase,
    ParallelNode,
    StartNode,
)

# --------------------------------------------------------------------------- 位置


@dataclass(frozen=True, slots=True)
class Cursor:
    """令牌位置。

    **为什么不能只用 node_key**：同一个条件分支里的节点，只有连同「走的是哪条
    分支」才唯一。`gates` 是分支决策链，形如 `("s2:s2a",)`，嵌套时累积。

    这个设计让**祖先判定退化成前缀比较**：
    「A 是不是 B 的祖先」⇔ `B.gates[:len(A.gates)] == A.gates` 且 A 在链上。
    退回时的取消范围因此可以写成纯函数（见 router.cancel_set_for_return）。
    """

    node_key: str
    gates: tuple[str, ...] = ()
    round: int = 1

    def __str__(self) -> str:  # pragma: no cover - 调试用
        return f"{self.node_key}{'@' + '/'.join(self.gates) if self.gates else ''}#r{self.round}"


@dataclass(frozen=True, slots=True)
class Placement:
    """节点在流程结构里的位置。用于「这个节点走完之后去哪」。"""

    kind: Literal["root", "branch", "parallel"]
    index: int = 0
    #: kind=branch
    condition_id: str | None = None
    branch_id: str | None = None
    #: kind=parallel
    parallel_id: str | None = None


@dataclass(frozen=True, slots=True)
class NodeDef:
    """编译后的节点。`raw` 保留原 pydantic 对象，便于读取类型专属字段。"""

    id: str
    type: str
    name: str
    raw: NodeBase
    placement: Placement
    #: 该节点所在位置的分支决策链
    gates: tuple[str, ...] = ()

    @property
    def is_blocking(self) -> bool:
        """是否占用令牌、阻塞主线。抄送不阻塞（PRD §3.3.2）。"""
        return self.type != "cc"

    @property
    def is_approval_like(self) -> bool:
        return self.type in {"approval", "fill"}


# --------------------------------------------------------------------------- 编译产物


@dataclass
class CompiledFlow:
    """流程定义编译后的可执行形态。

    构建请用 `compile.compile_flow()`，不要直接实例化。
    """

    definition: FlowDefinition
    start: NodeDef
    end: NodeDef
    nodes: dict[str, NodeDef]

    #: 顶层步骤顺序
    root_list: list[str] = field(default_factory=list)
    #: (条件节点id, 分支id) -> 该分支内的步骤顺序
    branch_lists: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    #: 并行容器id -> 成员节点id列表（按声明序）
    parallel_members: dict[str, list[str]] = field(default_factory=dict)
    #: 条件节点id -> 分支列表（保持声明序，用于按序求值）
    condition_branches: dict[str, list[Branch]] = field(default_factory=dict)

    # ---- 位置查询 ----

    def placement_of(self, node_id: str) -> Placement:
        return self.nodes[node_id].placement

    def branch_gates(self, node_id: str) -> tuple[str, ...]:
        return self.nodes[node_id].gates

    def ancestors(self, cursor: Cursor) -> list[str]:
        """从 start 到该位置经过的节点链（含自身）。

        沿容器层级**自下而上**收集再拼起来，不做图遍历 —— 结构是树，
        父链是唯一的。用于退回目标候选与进度条。
        """
        chain: list[str] = []
        current_id: str | None = cursor.node_key

        while current_id is not None:
            placement = self.nodes[current_id].placement

            if placement.kind == "root":
                chain = self.root_list[: placement.index + 1] + chain
                break

            if placement.kind == "branch":
                assert placement.condition_id and placement.branch_id
                seq = self.branch_lists.get((placement.condition_id, placement.branch_id), [])
                chain = seq[: placement.index + 1] + chain
                # 从分支弹到条件节点自身，继续向上
                current_id = placement.condition_id
                continue

            # 并行组：成员自身先入链，再爬到容器节点
            if not chain or chain[0] != current_id:
                chain = [current_id, *chain]
            assert placement.parallel_id
            current_id = placement.parallel_id

        return chain

    def return_target_candidates(self, cursor: Cursor) -> list[NodeDef]:
        """可退回的候选节点（PRD §3.5.4）。

        只有审批/填写节点有意义 —— 条件、并行容器、抄送都没有「待办」概念。
        且必须严格早于当前位置（不能退到自己）。
        """
        chain = self.ancestors(cursor)
        # 去掉自身
        if chain and chain[-1] == cursor.node_key:
            chain = chain[:-1]
        return [self.nodes[nid] for nid in chain if self.nodes[nid].is_approval_like]

    def linear_order(self, gates: Sequence[str]) -> list[str]:
        """给定分支上下文，返回主线的线性节点顺序（进度条用）。"""
        if not gates:
            return list(self.root_list)
        cond_id, branch_id = gates[-1].split(":", 1)
        return list(self.branch_lists.get((cond_id, branch_id), []))

    def describe_path(self, node_id: str) -> str:
        """人类可读的节点路径，用于错误信息。"""
        node = self.nodes.get(node_id)
        if node is None:
            return node_id
        if not node.gates:
            return node.name
        labels = []
        for gate in node.gates:
            cond_id, branch_id = gate.split(":", 1)
            cond = self.nodes.get(cond_id)
            branch = next(
                (b for b in self.condition_branches.get(cond_id, []) if b.id == branch_id),
                None,
            )
            if cond is not None:
                labels.append(f"{cond.name}/{(branch.name if branch and branch.name else branch_id)}")
        return " → ".join([*labels, node.name])


# --------------------------------------------------------------------------- 令牌操作


@dataclass(frozen=True, slots=True)
class TokenOp:
    """对令牌（tasks 行）的一次操作意图。

    引擎只产出这些意图，落库由 service 层完成 —— 这样纯核心可以脱离数据库测试。
    """

    kind: Literal["spawn", "cancel"]
    node_key: str
    gates: tuple[str, ...] = ()
    group_id: str | None = None
    #: 解析出的审批人 id（spawn 时）
    assignee_ids: tuple[int, ...] = ()
    #: 未命中审批人时转交的管理员 id
    fallback_admin_id: int | None = None
    abnormal: bool = False
    abnormal_reason: str | None = None
    reason: str | None = None

    @property
    def cursor(self) -> Cursor:
        return Cursor(self.node_key, self.gates)

    @property
    def is_abnormal(self) -> bool:
        return self.abnormal or self.fallback_admin_id is not None


@dataclass(frozen=True, slots=True)
class NotificationDraft:
    """待写入的通知。去重键由 service 层落到唯一索引。"""

    user_id: int
    type: str
    title: str
    content: str | None = None
    link: str | None = None
    dedup_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EngineEvent:
    """引擎事件。§8 交付物「引擎事件表」的运行时形态，也可落库用于调试。"""

    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    at: datetime | None = None


@dataclass
class EngineResult:
    """一次引擎事件的完整产物。service 层据此落库并生成通知。"""

    instance_status: str
    spawned: list[TokenOp] = field(default_factory=list)
    cancelled: list[TokenOp] = field(default_factory=list)
    notifications: list[NotificationDraft] = field(default_factory=list)
    events: list[EngineEvent] = field(default_factory=list)
    #: 本次动作产生的字段 diff（由 service 层填充）
    changed_fields: list[dict[str, Any]] = field(default_factory=list)
    action_id: int | None = None
    snapshot_id: int | None = None


# --------------------------------------------------------------------------- 聚合


@dataclass(frozen=True, slots=True)
class AssignmentView:
    """聚合判定只需要 assignment 的几个字段，不依赖 ORM 对象。"""

    user_id: int
    status: str
    result: str | None = None
    seq: int = 0

    @property
    def is_pending(self) -> bool:
        return self.status == "PENDING"

    @property
    def is_done(self) -> bool:
        return self.status == "DONE"

    @property
    def is_cancelled(self) -> bool:
        return self.status == "CANCELLED"


@dataclass(frozen=True, slots=True)
class TaskView:
    """聚合判定只需要 task 的几个字段。"""

    id: int
    node_key: str
    node_type: str
    status: str
    assignee_mode: str | None = None


NodeState = Literal["OPEN", "DONE", "FAILED"]
GroupState = Literal["OPEN", "JOINED", "FAILED"]


# --------------------------------------------------------------------------- 动作


@dataclass(frozen=True, slots=True)
class ActionContext:
    """一次用户动作的输入。"""

    action: Literal["AGREE", "REJECT", "RETURN", "SUBMIT"]
    actor_id: int
    opinion: str | None = None
    return_target: str | None = None
    attachment_ids: tuple[int, ...] = ()
    field_patch: Mapping[str, Any] = field(default_factory=dict)


#: 节点类型 → 中文名，供通知文案使用
NODE_TYPE_LABELS: dict[str, str] = {
    "start": "发起",
    "approval": "审批",
    "fill": "填写",
    "parallel": "并行",
    "condition": "条件",
    "cc": "抄送",
    "end": "结束",
}

__all__ = [
    "ActionContext",
    "AssignmentView",
    "CompiledFlow",
    "Cursor",
    "EngineEvent",
    "EngineResult",
    "GroupState",
    "NODE_TYPE_LABELS",
    "NodeDef",
    "NodeState",
    "NotificationDraft",
    "Placement",
    "TaskView",
    "TokenOp",
    # 便于其他模块从这里取节点类型，避免到处 import schemas
    "ApprovalNode",
    "Branch",
    "CcNode",
    "ConditionNode",
    "EndNode",
    "FillNode",
    "FlowDefinition",
    "NodeBase",
    "ParallelNode",
    "StartNode",
]
