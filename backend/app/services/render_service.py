"""实例详情页的渲染装配（PRD §5「实例详情页是全部价值的交汇点」）。

`render_instance()` 一次给出页面需要的全部东西，避免前端发五六个请求
再自己拼装（那样很容易出现「进度条已更新但表单还是旧的」这类撕裂状态）。

**字段权限按查看者身份分三档**（PRD §3.4 / §2 可见性）：

| 查看者 | 用哪套权限 | 效果 |
|---|---|---|
| 当前处理人（有待办） | 该节点的权限矩阵 | 可编辑本节点开放的字段 |
| 任意人看已终态实例 | 归档视角（全可见只读） | 补充字段此时才揭晓 |
| 其他（发起人 / 历史处理人 / 运行中） | **发起节点**权限 | 补充字段仍隐藏 |

第三档是 PRD 验收点的关键：「申请人全程看不到实际核销金额，直至通过后归档可见」。
早期若用「全可见只读」兜底，就会把这个字段提前泄露给发起人。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    TERMINAL_STATUSES,
    AssignmentStatus,
    TaskStatus,
    TaskType,
)
from app.engine.compile import compile_definition
from app.engine.permissions import (
    FieldPermission,
    resolve_field_permissions,
    resolve_view_permissions,
)
from app.engine.router import allowed_return_targets
from app.engine.types import NODE_TYPE_LABELS, CompiledFlow, Cursor
from app.models import (
    DataSnapshot,
    FlowInstance,
    Task,
    TaskAssignment,
    User,
)
from app.services import instance_service, snapshot_service, timeline_service


def render_instance(
    db: Session,
    instance: FlowInstance,
    *,
    viewer: User,
    assignment_id: int | None = None,
    snapshot_id: int | None = None,
) -> dict[str, Any]:
    """详情页的完整数据。

    `assignment_id` 指定「以哪个待办的身份查看」（会签时一个人可能有多条）；
    不给则自动找他当前在本实例上的待办。
    `snapshot_id` 指定查看某个历史时点（F4.6），此时权限一律按归档视角。
    """
    instance_service.assert_can_view(db, instance, viewer)

    version = instance_service.version_of(db, instance)
    compiled = compile_definition(version.definition)
    form_schema = instance_service.form_schema_of(db, instance)

    # ---- 当前待办（决定权限与可执行动作）----
    assignment = _resolve_assignment(db, instance, viewer, assignment_id)
    current_node = compiled.nodes.get(assignment.task.node_key) if assignment else None

    # ---- 数据（当前或历史时点）----
    if snapshot_id is not None:
        snapshot = db.get(DataSnapshot, snapshot_id)
        if snapshot is None or snapshot.instance_id != instance.id:
            from app.core.errors import NotFoundError

            raise NotFoundError("快照不存在", code="SNAPSHOT_NOT_FOUND")
        values = snapshot.data.get("values", {})
        viewing_snapshot = snapshot_service.to_out(db, snapshot)
    else:
        values = instance.current_data or {}
        viewing_snapshot = None

    # ---- 字段权限 ----
    permissions = _resolve_permissions(
        db, instance, compiled=compiled, form_schema=form_schema,
        viewer=viewer, assignment=assignment, snapshot=snapshot_id is not None,
    )

    # ---- 可执行动作 ----
    allowed_actions: list[str] = []
    return_targets: list[dict[str, Any]] = []
    if assignment is not None and current_node is not None:
        allowed_actions = _allowed_actions(current_node)
        if "RETURN" in allowed_actions:
            return_targets = [
                {"node_id": t.id, "name": t.name, "type": t.type}
                for t in allowed_return_targets(
                    compiled, Cursor(current_node.id, tuple(assignment.task.gates), instance.round)
                )
            ]

    # ---- 我在这张单上的角色 ----
    my_role = _viewer_role(db, instance, viewer, assignment)

    return {
        "instance": instance_service.to_out(db, instance, viewer=viewer),
        "my_role": my_role,
        "assignment": _assignment_out(assignment) if assignment else None,
        "current_node": (
            {
                "node_id": current_node.id,
                "name": current_node.name,
                "type": current_node.type,
                "type_label": NODE_TYPE_LABELS.get(current_node.type, current_node.type),
                "assignee_mode": assignment.task.assignee_mode,
                "opinion_required": bool(getattr(current_node.raw, "opinion_required", False)),
                "attachment_required": bool(getattr(current_node.raw, "attachment_required", False)),
            }
            if current_node and assignment
            else None
        ),
        "schema_data": version and _schema_json(db, instance),
        "values": values,
        "permissions": {k: v.to_dict() for k, v in permissions.items()},
        "progress": build_progress(db, instance, compiled),
        "actions": timeline_service.list_actions(db, instance),
        "allowed_actions": allowed_actions,
        "return_targets": return_targets,
        "attachments": _instance_attachments(db, instance),
        "snapshot": viewing_snapshot,
        "ext_fields": _ext_fields(instance),
    }


def _schema_json(db: Session, instance: FlowInstance) -> dict[str, Any]:
    from app.models import FormVersion

    form_version = db.get(FormVersion, instance.form_version_id)
    return form_version.schema if form_version else {}


# --------------------------------------------------------------------------- 权限


def _resolve_assignment(
    db: Session, instance: FlowInstance, viewer: User, assignment_id: int | None
) -> TaskAssignment | None:
    """找查看者在本实例上的待办。优先用显式指定的那条。"""
    if assignment_id is not None:
        assignment = db.get(TaskAssignment, assignment_id)
        if assignment is None or assignment.instance_id != instance.id:
            return None
        if assignment.user_id != viewer.id:
            return None
        return assignment

    return db.scalar(
        select(TaskAssignment)
        .where(
            TaskAssignment.instance_id == instance.id,
            TaskAssignment.user_id == viewer.id,
            TaskAssignment.status == AssignmentStatus.PENDING,
        )
        .order_by(TaskAssignment.id)
        .limit(1)
    )


def _resolve_permissions(
    db: Session,
    instance: FlowInstance,
    *,
    compiled: CompiledFlow,
    form_schema,
    viewer: User,
    assignment: TaskAssignment | None,
    snapshot: bool,
) -> dict[str, FieldPermission]:
    # 看历史快照 → 一律归档视角（历史没有「现在谁在处理」这回事）
    if snapshot:
        return resolve_view_permissions(form_schema)

    # 当前处理人 → 该节点的权限矩阵
    if assignment is not None:
        task = assignment.task
        node = compiled.nodes.get(task.node_key)
        if node is not None:
            rule = getattr(node.raw, "fields_permission", None)
            return resolve_field_permissions(
                form_schema=form_schema,
                node_type=node.type,
                rule=rule,
                values=instance.current_data or {},
            )

    # 已终态 → 归档视角：补充字段此时才揭晓（PRD 验收点）
    if instance.status in TERMINAL_STATUSES:
        return resolve_view_permissions(form_schema)

    # 运行中的其他相关人（发起人 / 已完成的历史处理人）→ 严格按发起阶段能看到的来，
    # 避免补充字段提前泄露给申请人
    return resolve_field_permissions(
        form_schema=form_schema,
        node_type="start",
        rule=compiled.definition.start.fields_permission,
        values=instance.current_data or {},
    )


def _allowed_actions(node) -> list[str]:
    if node.type == "approval":
        actions = ["AGREE", "RETURN"]
        if getattr(node.raw, "reject_policy", "") != "reject_forbidden":
            actions.insert(1, "REJECT")
        return actions
    if node.type == "fill":
        return ["SUBMIT", "RETURN"]
    return []


def _viewer_role(
    db: Session, instance: FlowInstance, viewer: User, assignment: TaskAssignment | None
) -> str:
    from app.core.policy import is_admin

    if assignment is not None:
        return "CURRENT_HANDLER"
    if is_admin(viewer):
        return "ADMIN"
    if instance.initiator_id == viewer.id:
        return "INITIATOR"

    row = db.scalar(
        select(TaskAssignment.id)
        .join(Task, Task.id == TaskAssignment.task_id)
        .where(
            TaskAssignment.instance_id == instance.id,
            TaskAssignment.user_id == viewer.id,
            Task.node_type == TaskType.CC,
        )
        .limit(1)
    )
    if row is not None:
        return "CC"
    return "PARTICIPANT"


# --------------------------------------------------------------------------- 进度条


def build_progress(db: Session, instance: FlowInstance, compiled: CompiledFlow) -> list[dict[str, Any]]:
    """进度条数据（F4.2）。

    并行组的成员**并列展示**；条件分支标出实际走的是哪条。
    """
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.instance_id == instance.id)
            .order_by(Task.id)
        ).all()
    )
    by_node: dict[str, list[Task]] = {}
    for task in tasks:
        by_node.setdefault(task.node_key, []).append(task)

    taken_gates = {
        gate
        for task in tasks
        for gate in (task.gates or [])
    }

    # 一次查出全部处理人姓名 —— 进度条上每个节点都要显示人名，逐个查会 N+1
    names = _user_names(db, {a.user_id for t in tasks for a in t.assignments})

    def node_entry(node_id: str) -> dict[str, Any]:
        node = compiled.nodes[node_id]
        node_tasks = by_node.get(node_id, [])
        return {
            "node_id": node.id,
            "name": node.name,
            "type": node.type,
            "type_label": NODE_TYPE_LABELS.get(node.type, node.type),
            "status": _node_status(node_tasks),
            "activation_seq": node_tasks[-1].activation_seq if node_tasks else 0,
            "assignees": _assignee_names(node_tasks, names),
            "completed_at": _last_completed(node_tasks),
        }

    out: list[dict[str, Any]] = []
    for node_id in compiled.root_list:
        node = compiled.nodes[node_id]
        if node.type == "condition":
            out.append({
                "node_id": node.id,
                "name": node.name,
                "type": "condition",
                "type_label": NODE_TYPE_LABELS["condition"],
                "branches": [
                    {
                        "branch_id": branch.id,
                        "name": branch.name or branch.id,
                        "is_else": branch.when is None,
                        "taken": f"{node.id}:{branch.id}" in taken_gates,
                        "nodes": [
                            node_entry(child)
                            for child in compiled.branch_lists.get((node.id, branch.id), [])
                        ],
                    }
                    for branch in compiled.condition_branches.get(node.id, [])
                ],
            })
            continue
        if node.type == "parallel":
            out.append({
                "node_id": node.id,
                "name": node.name,
                "type": "parallel",
                "type_label": NODE_TYPE_LABELS["parallel"],
                "mode": getattr(node.raw, "mode", "all"),
                "status": _parallel_status(by_node, compiled, node.id),
                "members": [
                    node_entry(m) for m in compiled.parallel_members.get(node.id, [])
                ],
            })
            continue
        out.append(node_entry(node_id))
    return out


def _user_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    from app.models import User as UserModel

    rows = db.execute(
        select(UserModel.id, UserModel.real_name).where(UserModel.id.in_(user_ids))
    ).all()
    return {uid: name for uid, name in rows}


def _node_status(node_tasks: list[Task]) -> str:
    if not node_tasks:
        return "PENDING"   # 还没走到
    if any(t.status == TaskStatus.PENDING for t in node_tasks):
        return "ACTIVE"
    if any(t.status == TaskStatus.COMPLETED for t in node_tasks):
        return "COMPLETED"
    return "CANCELLED"


def _parallel_status(by_node: dict[str, list[Task]], compiled: CompiledFlow, container_id: str) -> str:
    members = compiled.parallel_members.get(container_id, [])
    statuses = [_node_status(by_node.get(m, [])) for m in members]
    if not statuses or all(s == "PENDING" for s in statuses):
        return "PENDING"
    if any(s == "ACTIVE" for s in statuses):
        return "ACTIVE"
    if any(s == "CANCELLED" for s in statuses):
        return "CANCELLED"
    return "COMPLETED"


def _assignee_names(
    node_tasks: list[Task], names: Mapping[int, str] | None = None
) -> list[dict[str, Any]]:
    """处理人（含结果），供进度条上的人名与状态点。

    `names` 由调用方一次性批量查出 —— 逐个 assignment 去查用户会 N+1。
    """
    names = names or {}
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for task in node_tasks:
        for assignment in task.assignments:
            key = (assignment.user_id, assignment.status)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "assignment_id": assignment.id,
                "user_id": assignment.user_id,
                "user_name": names.get(assignment.user_id, f"#{assignment.user_id}"),
                "status": assignment.status,
                "result": assignment.result,
                "is_read": assignment.is_read,
            })
    return out


def _last_completed(node_tasks: list[Task]):
    stamps = [t.completed_at for t in node_tasks if t.completed_at]
    return max(stamps) if stamps else None


# --------------------------------------------------------------------------- 附件与扩展字段


def _instance_attachments(db: Session, instance: FlowInstance) -> list[dict[str, Any]]:
    """实例上的「补充附件」区（F4.4）：所有节点处理时上传的附件汇总。"""
    from app.models import Attachment
    from app.services import file_service

    rows = db.scalars(
        select(Attachment)
        .where(Attachment.instance_id == instance.id, Attachment.status == "BOUND")
        .order_by(Attachment.id)
    ).all()
    return [file_service.describe(a) for a in rows]


def _ext_fields(instance: FlowInstance) -> list[dict[str, Any]]:
    """机制 C 的动态字段（M5 才有数据，这里先给出结构）。"""
    return [
        {
            "field_key": f.field_key,
            "label": f.label,
            "type": f.type,
            "required": f.required,
            "status": f.status,
            "editable_node_ids": f.editable_node_ids,
            "visible_from_node_id": f.visible_from_node_id,
        }
        for f in instance.ext_fields
        if f.status == "ACTIVE"
    ]


def _assignment_out(assignment: TaskAssignment) -> dict[str, Any]:
    return {
        "assignment_id": assignment.id,
        "task_id": assignment.task_id,
        "user_id": assignment.user_id,
        "status": assignment.status,
        "seq": assignment.seq,
        "acted_at": assignment.acted_at,
    }
