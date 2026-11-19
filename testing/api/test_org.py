from __future__ import annotations

import uuid
from typing import Any, Callable

from support.client import ApiClient
from support.factories import (
    create_dept,
    create_draft,
    leave_data,
    submit,
    todo,
)


def _code(prefix: str) -> str:
    return f"E2E_{prefix}_{uuid.uuid4().hex[:8].upper()}"


def _instance_tasks(client: ApiClient, instance_id: int) -> list[dict[str, Any]]:
    return [item for item in todo(client) if item["instance_id"] == instance_id]


def test_dept_manager_upward_resolution(
    admin_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
    make_user: Callable[..., tuple[ApiClient, dict[str, Any]]],
) -> None:
    hq = seed["depts"]["HQ"]
    lisi_id = seed["users"]["lisi"]["id"]

    parent = create_dept(
        admin_client,
        name="E2E 主管父部门",
        code=_code("PARENT"),
        parent_id=hq["id"],
        manager_user_id=lisi_id,
    )
    child = create_dept(
        admin_client,
        name="E2E 无主管子部门",
        code=_code("CHILD"),
        parent_id=parent["id"],
    )
    employee_client, _ = make_user(dept_id=child["id"])
    try:
        data = leave_data(reason="D-01 向上查找")
        instance = create_draft(employee_client, seed["leave_flow"]["id"], data)
        response = submit(employee_client, instance["id"], data)
        assert response.status_code == 200, response.text
        submitted = response.json()
        assert submitted["status"] == "RUNNING"

        tasks = _instance_tasks(lisi_client, instance["id"])
        assert len(tasks) == 1, "子部门无主管时应向上找到父部门主管"
        assert tasks[0]["user_id"] == lisi_id
        assert tasks[0]["node_name"] == "直属上级审批"
        assert _instance_tasks(employee_client, instance["id"]) == []
    finally:
        employee_client.close()


def test_no_manager_falls_back_to_admin_and_marks_abnormal(
    admin_client: ApiClient,
    seed: dict[str, Any],
    make_user: Callable[..., tuple[ApiClient, dict[str, Any]]],
) -> None:
    root = create_dept(
        admin_client,
        name="E2E 独立根部门",
        code=_code("ROOT"),
        parent_id=None,
        manager_user_id=None,
    )
    child = create_dept(
        admin_client,
        name="E2E 独立子部门",
        code=_code("LEAF"),
        parent_id=root["id"],
        manager_user_id=None,
    )
    employee_client, _ = make_user(dept_id=child["id"])
    try:
        data = leave_data(reason="D-01 无主管兜底")
        instance = create_draft(employee_client, seed["leave_flow"]["id"], data)
        response = submit(employee_client, instance["id"], data)
        assert response.status_code == 200, response.text
        submitted = response.json()
        assert submitted["status"] == "RUNNING"
        assert submitted["abnormal"] is True

        tasks = _instance_tasks(admin_client, instance["id"])
        assert len(tasks) == 1, "没有任何主管时应转平台管理员"
        assert tasks[0]["user_id"] == seed["users"]["admin"]["id"]
    finally:
        employee_client.close()


def test_non_admin_cannot_manage_org(zhangsan_client: ApiClient) -> None:
    user = zhangsan_client.post(
        "users",
        json={
            "username": "e2e_forbidden_user",
            "password": "testPass123",
            "real_name": "Forbidden",
        },
    )
    assert user.status_code in (403, 404), user.text

    dept = zhangsan_client.post(
        "departments",
        json={"name": "Forbidden", "code": _code("FORBID")},
    )
    assert dept.status_code in (403, 404), dept.text

    audit = zhangsan_client.get("admin/audit-logs")
    assert audit.status_code in (403, 404), audit.text
