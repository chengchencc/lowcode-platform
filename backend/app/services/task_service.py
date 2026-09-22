"""任务查询与动作入口（F4.1 / F4.3）。

「我的待办」直接查 `task_assignments`（它冗余了 instance_id），
不必 join `tasks`，单表就能满足列表页的筛选与分页。

**会签组**：同一节点的多个待办分属不同人，各自是独立行；
列表里带上 `group_id` 与 `group_member_count`，前端据此做「同时待我处理」的提示。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.constants import AssignmentStatus, InstanceStatus, TaskStatus, TaskType
from app.core.errors import NotFoundError, UnprocessableError
from app.models import FlowInstance, FlowTemplate, Task, TaskAssignment, User
from app.services import instance_service


def get_assignment_or_404(db: Session, assignment_id: int) -> TaskAssignment:
    assignment = db.get(TaskAssignment, assignment_id)
    if assignment is None:
        raise NotFoundError("任务不存在", code="ASSIGNMENT_NOT_FOUND")
    return assignment


def get_task_or_404(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("任务不存在", code="TASK_NOT_FOUND")
    return task


# --------------------------------------------------------------------------- 列表

def build_todo_query(
    db: Session,
    *,
    user: User,
    keyword: str | None = None,
    flow_template_id: int | None = None,
) -> Select:
    stmt = (
        select(TaskAssignment)
        .join(Task, Task.id == TaskAssignment.task_id)
        .join(FlowInstance, FlowInstance.id == TaskAssignment.instance_id)
        .where(
            TaskAssignment.user_id == user.id,
            TaskAssignment.status == AssignmentStatus.PENDING,
            # 只看非抄送的待办（抄送在「抄送给我」里）
            Task.node_type != TaskType.CC,
        )
        .options(selectinload(TaskAssignment.task))
        .order_by(TaskAssignment.id.desc())
    )
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(FlowInstance.title.like(like) | FlowInstance.code.like(like))
    if flow_template_id is not None:
        stmt = stmt.where(FlowInstance.flow_template_id == flow_template_id)
    return stmt


def build_done_query(
    db: Session,
    *,
    user: User,
    keyword: str | None = None,
    flow_template_id: int | None = None,
) -> Select:
    stmt = (
        select(TaskAssignment)
        .join(Task, Task.id == TaskAssignment.task_id)
        .join(FlowInstance, FlowInstance.id == TaskAssignment.instance_id)
        .where(
            TaskAssignment.user_id == user.id,
            TaskAssignment.status == AssignmentStatus.DONE,
        )
        .options(selectinload(TaskAssignment.task))
        .order_by(TaskAssignment.acted_at.desc(), TaskAssignment.id.desc())
    )
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(FlowInstance.title.like(like) | FlowInstance.code.like(like))
    if flow_template_id is not None:
        stmt = stmt.where(FlowInstance.flow_template_id == flow_template_id)
    return stmt


def build_cc_query(
    db: Session, *, user: User, unread_only: bool = False, keyword: str | None = None
) -> Select:
    stmt = (
        select(TaskAssignment)
        .join(Task, Task.id == TaskAssignment.task_id)
        .join(FlowInstance, FlowInstance.id == TaskAssignment.instance_id)
        .where(
            TaskAssignment.user_id == user.id,
            Task.node_type == TaskType.CC,
        )
        .options(selectinload(TaskAssignment.task))
        .order_by(TaskAssignment.id.desc())
    )
    if unread_only:
        stmt = stmt.where(TaskAssignment.is_read.is_(False))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(FlowInstance.title.like(like) | FlowInstance.code.like(like))
    return stmt


def build_mine_query(
    db: Session,
    *,
    user: User,
    status: str | None = None,
    keyword: str | None = None,
) -> Select:
    stmt = (
        select(FlowInstance)
        .where(FlowInstance.initiator_id == user.id)
        .order_by(FlowInstance.id.desc())
    )
    if status:
        stmt = stmt.where(FlowInstance.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(FlowInstance.title.like(like) | FlowInstance.code.like(like))
    return stmt


# --------------------------------------------------------------------------- 装配


def _instance_briefs(db: Session, instance_ids: set[int]) -> dict[int, dict[str, Any]]:
    if not instance_ids:
        return {}
    rows = db.scalars(
        select(FlowInstance).where(FlowInstance.id.in_(instance_ids))
    ).all()
    template_ids = {r.flow_template_id for r in rows}
    templates = {
        t.id: t.name
        for t in db.scalars(select(FlowTemplate).where(FlowTemplate.id.in_(template_ids))).all()
    }
    initiator_ids = {r.initiator_id for r in rows}
    initiators = {
        u.id: u.real_name
        for u in db.scalars(select(User).where(User.id.in_(initiator_ids))).all()
    }
    return {
        r.id: {
            "instance_id": r.id,
            "instance_code": r.code,
            "instance_title": r.title,
            "instance_status": r.status,
            "round": r.round,
            "flow_template_id": r.flow_template_id,
            "flow_template_name": templates.get(r.flow_template_id),
            "initiator_id": r.initiator_id,
            "initiator_name": initiators.get(r.initiator_id),
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "last_action_at": r.last_action_at,
        }
        for r in rows
    }


def _group_sizes(db: Session, assignments: Sequence[TaskAssignment]) -> dict[str, int]:
    """同一 group_id 下还有多少待办 —— 用于「会签组」提示。"""
    group_ids = {a.task.group_id for a in assignments if a.task and a.task.group_id}
    if not group_ids:
        return {}
    rows = db.execute(
        select(Task.group_id, func.count(TaskAssignment.id))
        .join(TaskAssignment, TaskAssignment.task_id == Task.id)
        .where(
            Task.group_id.in_(group_ids),
            TaskAssignment.status == AssignmentStatus.PENDING,
            TaskAssignment.user_id.in_({a.user_id for a in assignments}),
        )
        .group_by(Task.group_id)
    ).all()
    return {gid: count for gid, count in rows}


def assignment_rows(
    db: Session, assignments: Sequence[TaskAssignment], *, include_group: bool = False
) -> list[dict[str, Any]]:
    briefs = _instance_briefs(db, {a.instance_id for a in assignments})
    groups = _group_sizes(db, assignments) if include_group else {}

    out: list[dict[str, Any]] = []
    for assignment in assignments:
        task = assignment.task
        row = {
            "assignment_id": assignment.id,
            "task_id": assignment.task_id,
            "user_id": assignment.user_id,
            "status": assignment.status,
            "result": assignment.result,
            "seq": assignment.seq,
            "is_read": assignment.is_read,
            "read_at": assignment.read_at,
            "acted_at": assignment.acted_at,
            "opinion": assignment.opinion,
            "node_key": task.node_key if task else None,
            "node_name": task.node_name if task else None,
            "node_type": task.node_type if task else None,
            "assignee_mode": task.assignee_mode if task else None,
            "round": task.round if task else None,
            "group_id": task.group_id if task else None,
            "activated_at": task.activated_at if task else None,
            **(briefs.get(assignment.instance_id) or {}),
        }
        if include_group and task and task.group_id:
            row["group_member_count"] = groups.get(task.group_id, 1)
        out.append(row)
    return out


def todo_summary(db: Session, user: User) -> dict[str, int]:
    """工作台角标用的计数。"""
    todo = db.scalar(
        select(func.count(TaskAssignment.id))
        .join(Task, Task.id == TaskAssignment.task_id)
        .where(
            TaskAssignment.user_id == user.id,
            TaskAssignment.status == AssignmentStatus.PENDING,
            Task.node_type != TaskType.CC,
        )
    ) or 0
    cc_unread = db.scalar(
        select(func.count(TaskAssignment.id))
        .join(Task, Task.id == TaskAssignment.task_id)
        .where(
            TaskAssignment.user_id == user.id,
            Task.node_type == TaskType.CC,
            TaskAssignment.is_read.is_(False),
        )
    ) or 0
    mine_running = db.scalar(
        select(func.count(FlowInstance.id)).where(
            FlowInstance.initiator_id == user.id,
            FlowInstance.status == InstanceStatus.RUNNING,
        )
    ) or 0
    return {"todo": todo, "cc_unread": cc_unread, "mine_running": mine_running}


# --------------------------------------------------------------------------- 动作


def act(
    db: Session,
    *,
    assignment_id: int,
    actor: User,
    action: str,
    opinion: str | None = None,
    attachment_ids: Sequence[int] = (),
    field_patch: Mapping[str, Any] | None = None,
    return_target: str | None = None,
    expected_version: int | None = None,
    request_id: str | None = None,
):
    """统一动作入口 —— 直接转发给引擎，这里只做一层薄封装。"""
    from app.services.instance_service import engine_for

    return engine_for(db).act(
        assignment_id=assignment_id,
        actor=actor,
        action=action,
        opinion=opinion,
        attachment_ids=attachment_ids,
        field_patch=field_patch,
        return_target=return_target,
        expected_version=expected_version,
        request_id=request_id,
    )


def return_targets_for(db: Session, assignment: TaskAssignment) -> list[dict[str, Any]]:
    """该待办可退回的节点（复用引擎规则，前端不重复实现）。"""
    from app.engine.compile import compile_definition
    from app.engine.router import allowed_return_targets
    from app.engine.types import Cursor

    task = assignment.task
    if task is None:
        raise UnprocessableError("任务已不存在", code="TASK_NOT_FOUND")

    instance = instance_service.get_or_404(db, assignment.instance_id)
    compiled = compile_definition(instance_service.version_of(db, instance).definition)
    node = compiled.nodes.get(task.node_key)
    if node is None:
        return []

    cursor = Cursor(node.id, tuple(task.gates), task.round)
    return [
        {"node_id": t.id, "name": t.name, "type": t.type}
        for t in allowed_return_targets(compiled, cursor)
    ]


def mark_read(db: Session, *, assignment_id: int, actor: User) -> None:
    from app.services.instance_service import engine_for

    engine_for(db).mark_cc_read(assignment_id=assignment_id, actor=actor)


def assert_task_open(task: Task) -> None:
    if task.status != TaskStatus.PENDING:
        raise UnprocessableError("该任务已结束", code="TASK_NOT_PENDING")
