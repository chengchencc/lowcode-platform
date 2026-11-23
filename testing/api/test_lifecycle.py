from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    act,
    approve_reimburse,
    assignments_for,
    cc_tasks,
    create_draft,
    find_assignment,
    leave_data,
    render,
    resubmit,
    submit,
    terminate,
    withdraw,
)


def _submit_leave(client: ApiClient, flow_id: int, reason: str) -> int:
    data = leave_data(reason=reason)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def test_reject_and_resubmit(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "REJECT-01 驳回重提")
    task = find_assignment(lisi_client, instance_id)

    rejected = act(lisi_client, task["assignment_id"], action="REJECT", opinion="材料不全")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"

    before = render(zhangsan_client, instance_id).json()
    assert before["instance"]["status"] == "REJECTED"
    assert any(action["action"] == "REJECT" for action in before["actions"])

    data = leave_data(reason="已补齐材料")
    again = resubmit(zhangsan_client, instance_id, data, note="已补齐")
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["status"] == "RUNNING"
    assert body["round"] == 2

    second_task = find_assignment(lisi_client, instance_id)
    assert second_task["round"] == 2
    assert act(lisi_client, second_task["assignment_id"], opinion="通过").status_code == 200
    assert render(zhangsan_client, instance_id).json()["instance"]["status"] == "APPROVED"


def test_withdraw_before_any_processing(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "WITHDRAW-01 撤回")
    task = find_assignment(lisi_client, instance_id)

    response = withdraw(zhangsan_client, instance_id, reason="不办了")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "WITHDRAWN"
    assert assignments_for(lisi_client, instance_id) == []

    late = act(lisi_client, task["assignment_id"], opinion="已撤回")
    assert late.status_code in (400, 403, 404, 409, 422), late.text
    assert render(zhangsan_client, instance_id).json()["instance"]["status"] == "WITHDRAWN"


def test_admin_terminate_running_and_non_admin_forbidden(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "TERMINATE-01 终止")
    assert assignments_for(lisi_client, instance_id)

    response = terminate(admin_client, instance_id, reason="测试终止")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "TERMINATED"
    assert assignments_for(lisi_client, instance_id) == []

    other_id = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "TERMINATE-01 越权")
    forbidden = terminate(lisi_client, other_id, reason="不应成功")
    assert forbidden.status_code in (403, 404), forbidden.text
    assert render(zhangsan_client, other_id).json()["instance"]["status"] == "RUNNING"


def test_cc_is_read_only_after_reimburse_approved(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = approve_reimburse(
        zhangsan=zhangsan_client,
        lisi=lisi_client,
        wangwu=wangwu_client,
        admin=admin_client,
        flow_id=seed["reimburse_flow"]["id"],
        reason="CC-01 抄送",
    )
    cc_items = [item for item in cc_tasks(wangwu_client) if item["instance_id"] == instance_id]
    assert len(cc_items) == 1
    cc = cc_items[0]
    assert cc["node_type"] == "CC"

    read = wangwu_client.post(f"tasks/assignments/{cc['assignment_id']}/read")
    assert read.status_code == 200, read.text

    # 抄送人没有处理权限
    acted = act(wangwu_client, cc["assignment_id"], opinion="不应成功")
    assert acted.status_code in (400, 403, 404, 409, 422), acted.text
