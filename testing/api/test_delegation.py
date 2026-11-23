from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from support.client import ApiClient
from support.factories import (
    act,
    cancel_delegation,
    create_delegation,
    create_dept,
    create_draft,
    find_assignment,
    leave_data,
    submit,
    todo,
    transfer,
)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def _submit_leave(client: ApiClient, flow_id: int, reason: str) -> int:
    data = leave_data(reason=reason)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def test_transfer_reassigns_pending_task(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "TASK-07 转办")
    task = find_assignment(lisi_client, instance_id)

    response = transfer(
        lisi_client,
        task["assignment_id"],
        to_user_id=seed["users"]["wangwu"]["id"],
        reason="请假交接",
    )
    assert response.status_code == 200, response.text

    assert [item for item in todo(lisi_client) if item["instance_id"] == instance_id] == []
    moved = find_assignment(wangwu_client, instance_id)
    assert moved["user_id"] == seed["users"]["wangwu"]["id"]

    approved = act(wangwu_client, moved["assignment_id"], opinion="代办同意")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"


def test_delegation_routes_new_task_to_delegatee(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
    make_user: Callable[..., tuple[ApiClient, dict[str, Any]]],
) -> None:
    # 独立部门/主管，避免影响种子账号 lisi 后续的审批测试
    delegator_client, delegator = make_user(name="e2e_delegator")
    dept = create_dept(
        admin_client,
        name="E2E 委托部门",
        code=f"E2E_DELEG_{uuid.uuid4().hex[:6].upper()}",
        parent_id=seed["depts"]["HQ"]["id"],
        manager_user_id=delegator["id"],
    )
    employee_client, _ = make_user(dept_id=dept["id"], name="e2e_delegatee_emp")

    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC) + timedelta(hours=1)
    created = create_delegation(
        delegator_client,
        delegatee_id=seed["users"]["wangwu"]["id"],
        start_at=_iso(start),
        end_at=_iso(end),
        reason="委托测试",
        flow_template_ids=[seed["leave_flow"]["id"]],
    )
    assert created.status_code in (200, 201), created.text
    delegation_id = created.json()["id"]

    try:
        instance_id = _submit_leave(employee_client, seed["leave_flow"]["id"], "TASK-07 委托")
        moved = find_assignment(wangwu_client, instance_id)
        assert moved["user_id"] == seed["users"]["wangwu"]["id"]
        assert [item for item in todo(delegator_client) if item["instance_id"] == instance_id] == []

        approved = act(wangwu_client, moved["assignment_id"], opinion="代理同意")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "APPROVED"

        # 委托人仍保留实例查看权（PHASE3 M14 §4.4）
        assert delegator_client.get(f"instances/{instance_id}/render").status_code == 200
    finally:
        cancel_delegation(delegator_client, delegation_id)
        employee_client.close()
        delegator_client.close()


def test_delegation_rejects_self_and_overlap(
    admin_client: ApiClient,
    seed: dict[str, Any],
    make_user: Callable[..., tuple[ApiClient, dict[str, Any]]],
) -> None:
    delegator_client, delegator = make_user(name="e2e_delegator_bad")
    dept = create_dept(
        admin_client,
        name="E2E 委托边界部门",
        code=f"E2E_DELEGB_{uuid.uuid4().hex[:6].upper()}",
        parent_id=seed["depts"]["HQ"]["id"],
        manager_user_id=delegator["id"],
    )
    assert dept["id"]
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC) + timedelta(hours=1)

    self_delegation = create_delegation(
        delegator_client,
        delegatee_id=delegator["id"],
        start_at=_iso(start),
        end_at=_iso(end),
        reason="自委托",
    )
    assert self_delegation.status_code in (400, 422), self_delegation.text

    first = create_delegation(
        delegator_client,
        delegatee_id=seed["users"]["wangwu"]["id"],
        start_at=_iso(start),
        end_at=_iso(end),
        reason="第一段",
    )
    assert first.status_code in (200, 201), first.text
    delegation_id = first.json()["id"]
    try:
        overlap = create_delegation(
            delegator_client,
            delegatee_id=seed["users"]["zhaoliu"]["id"],
            start_at=_iso(start),
            end_at=_iso(end),
            reason="重叠",
        )
        assert overlap.status_code in (400, 409, 422), overlap.text
    finally:
        cancel_delegation(delegator_client, delegation_id)
        delegator_client.close()
