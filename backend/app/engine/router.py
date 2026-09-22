"""令牌推进与取消范围计算（PRD §3.5.2 / §3.5.4）。

本模块是**纯函数集合**，不碰数据库 —— 引擎的语义正确性因此可以完整地单测覆盖。

三个概念：
- **位置（Cursor）**：`(node_key, gates, round)`，gates 是分支决策链
- **推进（plan_after_node）**：一个节点完成后，接下来该在哪些位置派发令牌
- **取消范围（cancel_set_for_return）**：退回时该取消哪些已有令牌

条件节点与并行组在推进时被**展开**：条件节点自身不产生令牌（求值后进入命中的
分支，空分支直接穿过），并行组展开成每个成员一个令牌。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.engine.conditions import pick_branch
from app.engine.errors import EngineError, FlowInvalid
from app.engine.types import CompiledFlow, Cursor, NodeDef

#: 并行组的成员完成后不能单独推进 —— 必须等聚合结果
_PARALLEL_MEMBER_MESSAGE = "并行组成员不能单独推进，应由组聚合决定后续"


def _gate(condition_id: str, branch_id: str) -> str:
    return f"{condition_id}:{branch_id}"


def plan_start(flow: CompiledFlow, values: Mapping[str, Any]) -> list[Cursor]:
    """提交时从哪里开始派发。"""
    if not flow.root_list:
        return [Cursor(flow.end.id)]
    return resolve_entry(flow, Cursor(flow.root_list[0]), values)


def resolve_entry(
    flow: CompiledFlow, cursor: Cursor, values: Mapping[str, Any]
) -> list[Cursor]:
    """把「到达某位置」展开成实际要派发令牌的位置。

    - 条件节点：求值后进入命中的分支；无命中且无 else、或分支为空 → 直接穿过
    - 并行组：展开成每个成员一个令牌
    - 其他：就是它自己
    """
    node = flow.nodes.get(cursor.node_key)
    if node is None:
        raise FlowInvalid(f"流程定义里没有节点 “{cursor.node_key}”", node_id=cursor.node_key)

    if node.type == "end":
        return [cursor]

    if node.type == "condition":
        branches = flow.condition_branches.get(node.id, [])
        branch = pick_branch(branches, values)
        if branch is None:
            # 全部不命中且没有「否则」分支 → 跳过条件节点继续往后
            return plan_after_node(flow, cursor, values)

        inner = flow.branch_lists.get((node.id, branch.id), [])
        if not inner:
            # 命中的是空分支 → 分支瞬间走完，等价于跳过
            return plan_after_node(flow, cursor, values)

        entered = Cursor(
            node_key=inner[0],
            gates=(*cursor.gates, _gate(node.id, branch.id)),
            round=cursor.round,
        )
        return resolve_entry(flow, entered, values)

    if node.type == "parallel":
        out: list[Cursor] = []
        for member_id in flow.parallel_members.get(node.id, []):
            out.extend(
                resolve_entry(flow, Cursor(member_id, cursor.gates, cursor.round), values)
            )
        return out

    return [cursor]


def _advance_placement(flow: CompiledFlow, node: NodeDef, cursor: Cursor) -> list[Cursor]:
    """按节点在其容器里的位置，走到下一个位置（不做条件展开）。"""
    placement = node.placement

    if placement.kind == "branch":
        assert placement.condition_id and placement.branch_id
        seq = flow.branch_lists.get((placement.condition_id, placement.branch_id), [])
        if placement.index + 1 < len(seq):
            return [
                Cursor(seq[placement.index + 1], cursor.gates, cursor.round)
            ]
        # 分支走完 → 弹回条件节点之后。分支那一层的 gate 要摘掉。
        outer = flow.nodes[placement.condition_id]
        return _advance_placement(flow, outer, Cursor(outer.id, cursor.gates[:-1], cursor.round))

    if placement.kind == "parallel":
        raise EngineError(_PARALLEL_MEMBER_MESSAGE)

    # root
    if placement.index + 1 < len(flow.root_list):
        return [Cursor(flow.root_list[placement.index + 1], cursor.gates, cursor.round)]
    return [Cursor(flow.end.id, (), cursor.round)]


def plan_after_node(
    flow: CompiledFlow, cursor: Cursor, values: Mapping[str, Any]
) -> list[Cursor]:
    """节点完成后，接下来该在哪些位置派发令牌。

    条件节点与并行组都会在这里被展开（返回的可能是多个位置）。
    """
    node = flow.nodes.get(cursor.node_key)
    if node is None:
        raise FlowInvalid(f"流程定义里没有节点 “{cursor.node_key}”", node_id=cursor.node_key)

    if node.placement.kind == "parallel" and node.type != "parallel":
        # 组内成员：由 group_state 聚合后调 plan_after_group
        raise EngineError(_PARALLEL_MEMBER_MESSAGE)

    nxt = _advance_placement(flow, node, cursor)
    out: list[Cursor] = []
    for position in nxt:
        out.extend(resolve_entry(flow, position, values))
    return out


def plan_after_group(
    flow: CompiledFlow, container_cursor: Cursor, values: Mapping[str, Any]
) -> list[Cursor]:
    """并行组聚合通过后，从容器位置继续往后。"""
    node = flow.nodes.get(container_cursor.node_key)
    if node is None or node.type != "parallel":
        raise FlowInvalid(
            f"“{container_cursor.node_key}” 不是并行组", node_id=container_cursor.node_key
        )
    nxt = _advance_placement(flow, node, container_cursor)
    out: list[Cursor] = []
    for position in nxt:
        out.extend(resolve_entry(flow, position, values))
    return out


# --------------------------------------------------------------------------- 退回


def allowed_return_targets(
    flow: CompiledFlow, cursor: Cursor
) -> list[NodeDef]:
    """当前节点可退回的目标集合（PRD §3.5.4）。

    节点上的 `return_targets`：
      - `None` → 允许退回全部前序审批/填写节点（默认，逐级向上）
      - `[]`   → 禁止退回
      - `["s1"]` → 仅允许这些
    """
    node = flow.nodes.get(cursor.node_key)
    if node is None or not node.is_approval_like:
        return []

    configured = getattr(node.raw, "return_targets", None)
    if configured is not None and len(configured) == 0:
        return []

    candidates = flow.return_target_candidates(cursor)
    if configured is None:
        return candidates

    allowed = set(configured)
    return [c for c in candidates if c.id in allowed]


def is_allowed_return_target(flow: CompiledFlow, cursor: Cursor, target_node_id: str) -> bool:
    return any(t.id == target_node_id for t in allowed_return_targets(flow, cursor))


def cancel_set_for_return(
    flow: CompiledFlow, pending: Sequence[Cursor], target: Cursor
) -> list[Cursor]:
    """退回时该取消哪些令牌。

    规则：**保留 target 的严格祖先**（那些位置在 target 之前，不该被撤销），
    其余全部取消 —— 包括 target 自身现有的待办、并行组内成员、或签的其余人、
    以及目标之后的所有顺序节点。

    随后由调用方在 target 上 `activation_seq + 1` 重新派发任务。

    已通过的更早节点不重走、字段数据不回滚 —— 都由「只取消令牌、不动数据」天然满足。

    注：V1 里这个集合**实际上总是全部待办令牌**（待办都处于当前前沿，而退回目标
    必然在前沿之前）。保留这个函数形态是为了把规则写成可测的纯函数，
    并且在 V2 引入并行分支/部分撤回时只需改这一处。
    """
    target_ancestors = set(flow.ancestors(target))
    target_ancestors.discard(target.node_key)  # 祖先不含自身
    return [c for c in pending if c.node_key not in target_ancestors]


# --------------------------------------------------------------------------- 便捷


def next_assignment_index(assignments: Sequence[Any]) -> int | None:
    """依次审批（SEQUENTIAL）模式下，下一个该被激活的 assignment 序号。

    `assignments` 需按 seq 升序，且元素带有 `seq` 与 `status`。
    全部处理完返回 None。
    """
    for item in sorted(assignments, key=lambda a: a.seq):
        if item.status in {"WAITING", "PENDING"}:
            return item.seq
    return None


def branch_of(flow: CompiledFlow, gates: Sequence[str]) -> tuple[str, str] | None:
    """从 gates 里取出最内层的 (条件节点id, 分支id)。"""
    if not gates:
        return None
    cond_id, _, branch_id = gates[-1].partition(":")
    if not branch_id:
        return None
    return cond_id, branch_id


__all__ = [
    "allowed_return_targets",
    "branch_of",
    "cancel_set_for_return",
    "is_allowed_return_target",
    "next_assignment_index",
    "plan_after_group",
    "plan_after_node",
    "plan_start",
    "resolve_entry",
]
