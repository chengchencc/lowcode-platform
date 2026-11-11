"""首页聚合（M11）。

只读、一次取全：个人计数 + 待办预览 + 我发起的 + 常用流程 + 管理概览。
统计口径复用 task_service / instance_service，不另起一套。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.core.constants import AssignmentStatus, InstanceStatus, TaskType
from app.core.policy import is_designer
from app.models import FlowInstance, FlowTemplate, Task, TaskAssignment, User
from app.services import instance_service, task_service, work_stat_service


def local_bounds(now: datetime | None = None) -> tuple[datetime, datetime, datetime]:
    """返回（今日 0 点、本周一 0 点、本月 1 日 0 点）的 **naive UTC** 时间。"""
    moment = now or utcnow()
    tz = ZoneInfo(settings.app_timezone)
    local = moment.replace(tzinfo=UTC).astimezone(tz)
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    week = day - timedelta(days=day.weekday())
    month = day.replace(day=1)

    def to_utc(value: datetime) -> datetime:
        return value.astimezone(UTC).replace(tzinfo=None)

    return to_utc(day), to_utc(week), to_utc(month)


def overview(db: Session, user: User, *, now: datetime | None = None) -> dict:
    day_start, week_start, month_start = local_bounds(now)

    counts = task_service.todo_summary(db, user)
    mine_finished = db.scalar(
        select(func.count(FlowInstance.id)).where(
            FlowInstance.initiator_id == user.id,
            FlowInstance.status == InstanceStatus.APPROVED,
            FlowInstance.finished_at >= month_start,
        )
    ) or 0

    todo_rows = list(
        db.scalars(task_service.build_todo_query(db, user=user).limit(5)).all()
    )
    todos = [
        {
            "assignment_id": row["assignment_id"],
            "instance_id": row["instance_id"],
            "title": row.get("instance_title") or "",
            "code": row.get("instance_code"),
            "node_name": row.get("node_name"),
            "arrived_at": row.get("activated_at"),
        }
        for row in task_service.assignment_rows(db, todo_rows)
    ]

    instances = list(
        db.scalars(
            select(FlowInstance)
            .where(FlowInstance.initiator_id == user.id)
            .order_by(FlowInstance.id.desc())
            .limit(5)
        ).all()
    )
    my_instances = [
        {
            "instance_id": item.id,
            "title": item.title,
            "status": item.status,
            "current_node_names": item.current_node_keys or [],
            "updated_at": item.last_action_at or item.updated_at,
        }
        for item in instances
    ]

    # 常用流程 = 可发起流程按「本人最近发起次数」排序；没发起过的排后面
    recent_rows = db.execute(
        select(FlowInstance.flow_template_id, func.count(FlowInstance.id))
        .where(FlowInstance.initiator_id == user.id)
        .group_by(FlowInstance.flow_template_id)
    ).all()
    recent = {flow_id: count for flow_id, count in recent_rows}
    available = instance_service.list_available_flows(db, user)
    available.sort(key=lambda item: (-recent.get(item["id"], 0), -item["id"]))
    quick_flows = [
        {
            "flow_template_id": item["id"],
            "name": item["name"],
            "icon": item.get("icon"),
        }
        for item in available[:6]
    ]

    admin = None
    if is_designer(user):
        running = db.scalar(
            select(func.count(FlowInstance.id)).where(
                FlowInstance.status == InstanceStatus.RUNNING
            )
        ) or 0
        submitted_today = db.scalar(
            select(func.count(FlowInstance.id)).where(FlowInstance.started_at >= day_start)
        ) or 0
        finished_week = db.scalar(
            select(func.count(FlowInstance.id)).where(
                FlowInstance.status == InstanceStatus.APPROVED,
                FlowInstance.finished_at >= week_start,
            )
        ) or 0
        backlog = db.scalar(
            select(func.count(TaskAssignment.id))
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(
                TaskAssignment.status == AssignmentStatus.PENDING,
                Task.node_type != TaskType.CC,
            )
        ) or 0
        by_flow = db.execute(
            select(
                FlowInstance.flow_template_id,
                FlowTemplate.name,
                func.count(FlowInstance.id),
            )
            .join(FlowTemplate, FlowTemplate.id == FlowInstance.flow_template_id)
            .where(FlowInstance.status == InstanceStatus.RUNNING)
            .group_by(FlowInstance.flow_template_id, FlowTemplate.name)
            .order_by(func.count(FlowInstance.id).desc(), FlowInstance.flow_template_id)
            .limit(5)
        ).all()
        admin = {
            "running": running,
            "submitted_today": submitted_today,
            "finished_this_week": finished_week,
            "pending_backlog": backlog,
            "by_flow": [
                {"flow_template_id": flow_id, "name": name, "count": count}
                for flow_id, name, count in by_flow
            ],
        }

    work_stats = [
        {
            "sheet_id": item["id"],
            "name": item["name"],
            "updated_at": item["updated_at"],
        }
        for item in work_stat_service.list_sheets(db, user)
    ]

    return {
        "personal": {**counts, "mine_finished_this_month": mine_finished},
        "todos": todos,
        "my_instances": my_instances,
        "quick_flows": quick_flows,
        "work_stats": work_stats,
        "admin": admin,
    }
