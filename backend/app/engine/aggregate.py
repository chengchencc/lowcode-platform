"""节点与并行组的聚合判定（PRD §3.5.3）。

对应关系：
- **节点内**：一个 `tasks` 行 + N 个 `task_assignments`（会签 all / 或签 any / 依次 sequential）
  → `node_state()`
- **并行组**：N 个 `tasks` 行共享 group_id
  → `group_state()`

两者逻辑相似但作用对象不同，刻意分开 —— 混在一起会让「组内成员的节点怎么算」
变得难以推理。

全是纯函数，输入是轻量的 View 对象（见 types.py 的 AssignmentView / TaskView），
不依赖 ORM，因而可以穷举测试。
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.constants import AggregateMode
from app.engine.types import AssignmentView, GroupState, NodeState, TaskView

#: 视为「通过」的处理结果
PASSING_RESULTS = frozenset({"AGREE", "SUBMIT"})
#: 视为「失败」的处理结果
FAILING_RESULTS = frozenset({"REJECT", "RETURN"})


def node_state(mode: str, assignments: Sequence[AssignmentView]) -> NodeState:
    """判定一个节点是否走完。

    | 模式 | 通过条件 | 失败条件 |
    |---|---|---|
    | SINGLE | 唯一处理人同意 | 该人驳回/退回 |
    | SEQUENTIAL | 全部依次同意 | 任一驳回/退回 |
    | ALL（会签） | 全部同意 | 任一驳回/退回 |
    | ANY（或签） | 任一同意 | 已有驳回/退回且无人同意 |
    """
    if not assignments:
        return "OPEN"

    # 失败优先于通过：只要有人驳回/退回，节点就失败。
    # 对 ANY 而言这条不会误伤 —— 一旦有人同意，其余人会被立即取消，
    # 不可能再出现「既有同意又有驳回」的状态。
    if any(a.is_done and a.result in FAILING_RESULTS for a in assignments):
        return "FAILED"

    if mode == AggregateMode.ANY:
        return "DONE" if any(a.is_done and a.result in PASSING_RESULTS for a in assignments) else "OPEN"

    # SINGLE / SEQUENTIAL / ALL 都是「全部通过才过」
    if all(a.is_done and a.result in PASSING_RESULTS for a in assignments):
        return "DONE"
    return "OPEN"


def group_state(mode: str, members: Sequence[TaskView]) -> GroupState:
    """判定并行组是否汇合。

    成员的 task 状态含义：`COMPLETED` = 该成员节点已通过，
    `CANCELLED` = 该成员失败或被取消，`PENDING` = 还在办理。

    | 模式 | 汇合条件 | 失败条件 |
    |---|---|---|
    | all | 全部成员通过 | 任一成员失败 |
    | any | 任一成员通过 | 全部成员都已失败（不可能再有人通过） |
    """
    if not members:
        return "JOINED"

    completed = [m for m in members if m.status == "COMPLETED"]
    cancelled = [m for m in members if m.status == "CANCELLED"]
    pending = [m for m in members if m.status == "PENDING"]

    if mode == AggregateMode.ANY:
        if completed:
            return "JOINED"
        # 还有人在办就再等等；全被打掉才算失败
        return "OPEN" if pending else "FAILED"

    # all（会签）
    if cancelled:
        return "FAILED"
    if len(completed) == len(members):
        return "JOINED"
    return "OPEN"


def should_cancel_siblings_on_pass(mode: str) -> bool:
    """该模式下，有人通过后是否要取消同节点的其余任务。

    只有或签（ANY）需要 —— 会签要等所有人。
    """
    return mode == AggregateMode.ANY


def next_sequential_seq(assignments: Sequence[AssignmentView]) -> int | None:
    """依次审批：下一个该被激活的 seq。

    没轮到的 assignment 状态是 WAITING，激活后变 PENDING。
    """
    ordered = sorted(assignments, key=lambda a: a.seq)
    for item in ordered:
        if item.status == "WAITING":
            return item.seq
        if item.status == "PENDING":
            return None  # 当前这个还没处理完，不激活下一个
    return None


def is_sequential(mode: str) -> bool:
    return mode == AggregateMode.SEQUENTIAL
