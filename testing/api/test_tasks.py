from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    act,
    create_draft,
    done,
    find_assignment,
    leave_data,
    mine,
    reimburse_data,
    render,
    submit,
    todo,
)


def _submit_leave(client: ApiClient, flow_id: int, reason: str) -> int:
    data = leave_data(reason=reason)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def test_leave_happy_path(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "TASK-01 正常审批")
    task = find_assignment(lisi_client, instance_id)
    assert task["node_name"] == "直属上级审批"

    response = act(lisi_client, task["assignment_id"], opinion="同意")
    assert response.status_code == 200, response.text
    instance = response.json()
    assert instance["status"] == "APPROVED"
    assert instance["finished_at"]

    assert any(item["instance_id"] == instance_id for item in done(lisi_client))
    # /tasks/mine 返回的是实例分页（InstanceOut），主键字段是 id。
    assert any(item["id"] == instance_id for item in mine(zhangsan_client))


def test_wrong_user_cannot_act(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "TASK-02 越权")
    task = find_assignment(lisi_client, instance_id)

    response = act(wangwu_client, task["assignment_id"], opinion="不应成功")
    assert response.status_code in (403, 404), response.text

    instance = render(zhangsan_client, instance_id)
    assert instance.status_code == 200, instance.text
    assert instance.json()["instance"]["status"] == "RUNNING"
    remaining = find_assignment(lisi_client, instance_id)
    assert remaining["status"] == "PENDING"


def test_act_twice_has_single_effect(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "TASK-06 重复处理")
    task = find_assignment(lisi_client, instance_id)

    first = act(lisi_client, task["assignment_id"], opinion="第一次")
    assert first.status_code == 200, first.text
    second = act(lisi_client, task["assignment_id"], opinion="第二次")
    assert second.status_code in (400, 403, 409, 422), second.text

    instance = render(zhangsan_client, instance_id).json()["instance"]
    assert instance["status"] == "APPROVED"
    assert instance["done_count"] == 1
    assert len([item for item in done(lisi_client) if item["instance_id"] == instance_id]) == 1


def test_reimburse_parallel_all_and_fill_node(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    data = reimburse_data(amount=2500, reason="TASK-03/04 并行会签")
    draft = create_draft(zhangsan_client, seed["reimburse_flow"]["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text
    instance_id = draft["id"]

    manager_task = find_assignment(lisi_client, instance_id)
    assert act(lisi_client, manager_task["assignment_id"], opinion="部门经理同意").status_code == 200

    finance_task = find_assignment(wangwu_client, instance_id)
    admin_task = find_assignment(admin_client, instance_id)
    assert finance_task["group_id"] == admin_task["group_id"]
    # 该字段是「当前用户在同一组里的待办条数」，前端标签为“同组 N 条”；
    # 不是组内总人数。每个会签成员各自看到 1 条。
    assert finance_task["group_member_count"] == 1
    assert admin_task["group_member_count"] == 1

    assert act(wangwu_client, finance_task["assignment_id"], opinion="财务同意").status_code == 200
    assert act(admin_client, admin_task["assignment_id"], opinion="管理员同意").status_code == 200

    fill_task = find_assignment(wangwu_client, instance_id, node_type="FILL")
    render_body = render(
        wangwu_client, instance_id, assignment_id=fill_task["assignment_id"]
    )
    assert render_body.status_code == 200, render_body.text
    permissions = render_body.json()["permissions"]
    assert permissions["actualAmount"]["visible"] is True
    assert permissions["actualAmount"]["editable"] is True
    assert permissions["actualAmount"]["required"] is True
    assert permissions["invoiceNo"]["editable"] is True

    filled = act(
        wangwu_client,
        fill_task["assignment_id"],
        action="SUBMIT",
        opinion="核销完成",
        field_patch={"actualAmount": 2500, "invoiceNo": "INV-E2E-001"},
    )
    assert filled.status_code == 200, filled.text
    assert filled.json()["status"] == "APPROVED"
