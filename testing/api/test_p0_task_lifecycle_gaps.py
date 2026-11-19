"""P0 补齐：任务列表、并行驳回、字段 diff、转办/撤回/终止通知、动态字段快照。"""

from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    _approval_node,
    act,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    find_assignment,
    parallel_all_definition,
    sequential_definition,
    simple_data,
    submit,
    todo,
    transfer,
    user_rule,
)


def _submit(client: ApiClient, flow_id: int, reason: str, amount: float = 100) -> int:
    data = simple_data(reason=reason, amount=amount)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def _notifications(client: ApiClient) -> list[dict[str, Any]]:
    response = client.get("notifications?size=100")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _has_notification(
    client: ApiClient, type_: str, instance_id: int | None = None
) -> bool:
    return any(
        item["type"] == type_
        and (
            instance_id is None
            or (item.get("payload") or {}).get("instance_id") == instance_id
        )
        for item in _notifications(client)
    )


def test_todo_list_paging_and_keyword(
    admin_client: ApiClient, zhangsan_client: ApiClient, lisi_client: ApiClient
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 列表分页表单")
    seed_users = admin_client.get("users?size=100").json()["items"]
    lisi_id = next(user["id"] for user in seed_users if user["username"] == "lisi")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 列表分页流程",
        definition=sequential_definition([("a1", "审批", lisi_id)]),
    )

    first = _submit(zhangsan_client, flow["id"], "列表-甲")
    second = _submit(zhangsan_client, flow["id"], "列表-乙")
    third = _submit(zhangsan_client, flow["id"], "列表-丙")

    page1 = lisi_client.get(
        "tasks/todo", params={"page": 1, "size": 2, "flow_template_id": flow["id"]}
    )
    assert page1.status_code == 200, page1.text
    body1 = page1.json()
    assert body1["total"] >= 3
    assert len(body1["items"]) == 2

    page2 = lisi_client.get(
        "tasks/todo", params={"page": 2, "size": 2, "flow_template_id": flow["id"]}
    ).json()
    assert page2["items"]

    instance_info = admin_client.get(f"instances/{first}/render").json()["instance"]
    by_code = lisi_client.get(
        "tasks/todo", params={"size": 100, "keyword": instance_info["code"]}
    ).json()["items"]
    assert [item["instance_id"] for item in by_code] == [first]

    by_title = lisi_client.get(
        "tasks/todo", params={"size": 100, "keyword": "列表-乙"}
    ).json()["items"]
    assert [item["instance_id"] for item in by_title] == [second]
    assert third not in [item["instance_id"] for item in by_title]


def test_parallel_all_reject_cancels_siblings(
    admin_client: ApiClient, zhangsan_client: ApiClient, lisi_client: ApiClient, wangwu_client: ApiClient
) -> None:
    users = admin_client.get("users?size=100").json()["items"]
    ids = {user["username"]: user["id"] for user in users}
    form = create_form_and_publish(admin_client, name="E2E 会签驳回表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 会签驳回流程",
        definition=parallel_all_definition([ids["lisi"], ids["wangwu"]]),
    )
    instance_id = _submit(zhangsan_client, flow["id"], "会签驳回")

    lisi_task = find_assignment(lisi_client, instance_id)
    rejected = act(lisi_client, lisi_task["assignment_id"], action="REJECT", opinion="驳回")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"

    assert [item for item in todo(wangwu_client) if item["instance_id"] == instance_id] == []
    assert _has_notification(wangwu_client, "TASK_CANCELLED", instance_id)


def test_action_field_patch_is_recorded_in_timeline(
    admin_client: ApiClient, zhangsan_client: ApiClient, lisi_client: ApiClient
) -> None:
    users = admin_client.get("users?size=100").json()["items"]
    lisi_id = next(user["id"] for user in users if user["username"] == "lisi")
    form = create_form_and_publish(admin_client, name="E2E 字段 Diff 表单")
    node = _approval_node("a1", "审批", user_rule(lisi_id))
    node["fields_permission"]["overrides"] = {"amount": "editable"}
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 字段 Diff 流程",
        definition={"steps": [node]},
    )
    instance_id = _submit(zhangsan_client, flow["id"], "字段 Diff", amount=100)
    task = find_assignment(lisi_client, instance_id)
    acted = act(
        lisi_client,
        task["assignment_id"],
        opinion="调整金额",
        field_patch={"amount": 200},
    )
    assert acted.status_code == 200, acted.text

    timeline = lisi_client.get(f"instances/{instance_id}/timeline").json()
    agree = next(item for item in timeline if item["action"] == "AGREE")
    assert agree["changed_fields"], agree
    assert any(item.get("key") == "amount" for item in agree["changed_fields"])
    assert agree["opinion"] == "调整金额"


def test_transfer_notifications_and_timeline(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
) -> None:
    users = admin_client.get("users?size=100").json()["items"]
    ids = {user["username"]: user["id"] for user in users}
    form = create_form_and_publish(admin_client, name="E2E 转办通知表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 转办通知流程",
        definition=sequential_definition([("a1", "审批", ids["lisi"])]),
    )
    instance_id = _submit(zhangsan_client, flow["id"], "转办通知")
    task = find_assignment(lisi_client, instance_id)

    moved = transfer(
        lisi_client,
        task["assignment_id"],
        to_user_id=ids["wangwu"],
        reason="出差转办",
    )
    assert moved.status_code == 200, moved.text

    assert _has_notification(wangwu_client, "TASK_TRANSFERRED", instance_id)
    assert _has_notification(lisi_client, "TASK_TRANSFERRED", instance_id)
    timeline = lisi_client.get(f"instances/{instance_id}/timeline").json()
    transfer_row = next(item for item in timeline if item["action"] == "TRANSFER")
    assert transfer_row["opinion"] == "出差转办"
    assert transfer_row["to_status"] == "RUNNING"


def test_withdraw_and_terminate_notifications(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
) -> None:
    users = admin_client.get("users?size=100").json()["items"]
    lisi_id = next(user["id"] for user in users if user["username"] == "lisi")
    form = create_form_and_publish(admin_client, name="E2E 终态通知表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 终态通知流程",
        definition=sequential_definition([("a1", "审批", lisi_id)]),
    )

    withdrawn = _submit(zhangsan_client, flow["id"], "撤回通知")
    assert zhangsan_client.post(f"instances/{withdrawn}/withdraw", json={}).status_code == 200
    assert _has_notification(zhangsan_client, "INSTANCE_WITHDRAWN", withdrawn)
    assert _has_notification(lisi_client, "TASK_CANCELLED", withdrawn)

    terminated = _submit(zhangsan_client, flow["id"], "终止通知")
    response = admin_client.post(
        f"instances/{terminated}/terminate", json={"reason": "项目取消"}
    )
    assert response.status_code == 200, response.text
    assert _has_notification(zhangsan_client, "INSTANCE_TERMINATED", terminated)
    assert _has_notification(lisi_client, "TASK_CANCELLED", terminated)


def test_ext_field_added_notification_and_snapshot(
    admin_client: ApiClient, zhangsan_client: ApiClient, lisi_client: ApiClient
) -> None:
    users = admin_client.get("users?size=100").json()["items"]
    lisi_id = next(user["id"] for user in users if user["username"] == "lisi")
    form = create_form_and_publish(admin_client, name="E2E 动态字段快照表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 动态字段快照流程",
        definition=sequential_definition([("a1", "审批", lisi_id)]),
    )
    instance_id = _submit(zhangsan_client, flow["id"], "动态字段快照")
    task = find_assignment(lisi_client, instance_id)

    added = admin_client.post(
        f"instances/{instance_id}/ext-fields",
        json={"label": "合同编号", "type": "text", "required": True},
    )
    assert added.status_code == 200, added.text
    ext_key = added.json()["ext_fields"][0]["field_key"]
    assert _has_notification(lisi_client, "EXT_FIELD_ADDED", instance_id)

    acted = act(
        lisi_client,
        task["assignment_id"],
        opinion="补充合同编号",
        field_patch={ext_key: "HT-SNAP-001"},
    )
    assert acted.status_code == 200, acted.text

    timeline = zhangsan_client.get(f"instances/{instance_id}/timeline").json()
    agree = next(item for item in timeline if item["action"] == "AGREE")
    snapshot = zhangsan_client.get(
        f"instances/{instance_id}/snapshots/{agree['snapshot_id']}"
    ).json()
    assert snapshot["data"]["values"].get(ext_key) == "HT-SNAP-001", snapshot
    assert any(
        item.get("field_key") == ext_key
        for item in snapshot["data"].get("ext_fields", [])
    ), snapshot
