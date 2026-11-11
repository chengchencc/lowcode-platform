"""首页聚合接口（M11）。"""

from __future__ import annotations

from datetime import datetime

from app.core.clock import utcnow
from app.core.constants import AssignmentStatus, InstanceStatus, TaskStatus
from app.models import Task, TaskAssignment
from tests.test_engine_service import (
    _draft_instance,
    _published_flow,
    _published_form,
    _user,
)

BASE = "/api/v1"


def _run_instance(
    db,
    initiator,
    *,
    status=InstanceStatus.RUNNING,
    started_at=None,
    finished_at=None,
):
    owner = _user(db)
    form = _published_form(db, owner)
    flow = _published_flow(db, owner, form, {"steps": []})
    instance = _draft_instance(db, flow, form, initiator)
    instance.status = status
    instance.started_at = started_at
    instance.finished_at = finished_at
    instance.current_node_keys = ["部门审批"]
    db.flush()
    return instance


def _assign(db, instance, user, *, node_type="approval"):
    task = Task(
        instance_id=instance.id,
        node_key="s1",
        node_name="部门审批",
        node_type=node_type,
        status=TaskStatus.PENDING,
        blocks_flow=True,
        node_def_snapshot={},
        gates=[],
        activation_seq=1,
    )
    db.add(task)
    db.flush()
    assignment = TaskAssignment(
        task_id=task.id,
        instance_id=instance.id,
        user_id=user.id,
        status=AssignmentStatus.PENDING,
        seq=0,
    )
    db.add(assignment)
    db.flush()
    return assignment


def test_dashboard_requires_login(client):
    assert client.get(f"{BASE}/dashboard/overview").status_code == 401


def test_dashboard_personal_overview(client, db, normal_headers, normal_user):
    instance = _run_instance(db, normal_user, started_at=utcnow())
    _assign(db, instance, normal_user)

    from app.schemas.work_stat import WorkStatColumn, WorkStatSheetCreate
    from app.services import work_stat_service

    work_stat_service.create_sheet(
        db,
        WorkStatSheetCreate(
            name="测试工作量",
            columns=[WorkStatColumn(key="c_name", label="姓名", type="text")],
        ),
        actor=normal_user,
    )

    resp = client.get(f"{BASE}/dashboard/overview", headers=normal_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["personal"]["todo"] == 1
    assert body["personal"]["mine_running"] == 1
    assert body["todos"][0]["title"] == "测试单据"
    assert body["todos"][0]["assignment_id"]
    assert body["my_instances"][0]["instance_id"] == instance.id
    assert body["quick_flows"], "可发起流程应出现在常用流程里"
    assert body["work_stats"][0]["name"] == "测试工作量"
    assert body["admin"] is None


def test_dashboard_admin_counts(client, db, admin_headers):
    from sqlalchemy import select

    from app.models import User

    admin = db.scalar(select(User).where(User.username == "admin"))
    running = _run_instance(db, admin, started_at=utcnow())
    _assign(db, running, admin)
    _run_instance(
        db,
        admin,
        status=InstanceStatus.APPROVED,
        started_at=utcnow(),
        finished_at=utcnow(),
    )

    resp = client.get(f"{BASE}/dashboard/overview", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    admin_block = resp.json()["admin"]

    assert admin_block["running"] >= 1
    assert admin_block["submitted_today"] >= 1
    assert admin_block["finished_this_week"] >= 1
    assert admin_block["pending_backlog"] >= 1
    assert admin_block["by_flow"], "运行中实例应按流程聚合"


def test_local_bounds_uses_configured_timezone():
    from app.services.dashboard_service import local_bounds

    # UTC 2026-11-11 16:30 = 本地（Asia/Shanghai）2026-11-12 00:30
    day, week, month = local_bounds(datetime(2026, 11, 11, 16, 30))
    assert day == datetime(2026, 11, 11, 16, 0)
    assert week == datetime(2026, 11, 8, 16, 0)  # 周一 11-09 00:00 本地
    assert month == datetime(2026, 10, 31, 16, 0)  # 11-01 00:00 本地
