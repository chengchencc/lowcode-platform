from __future__ import annotations

from support.client import ApiClient
from support.factories import (
    act,
    approve_reimburse,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    find_assignment,
    leave_data,
    parallel_any_definition,
    sequential_definition,
    submit,
    upload_file,
)


def test_opinion_and_attachment_required(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 必填意见表单")
    definition = sequential_definition(
        [("a1", "必填审批", seed["users"]["lisi"]["id"])]
    )
    definition["steps"][0]["opinion_required"] = True
    definition["steps"][0]["attachment_required"] = True
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 必填意见流程",
        definition=definition,
    )

    data = leave_data(reason="TASK-05 必填意见")
    draft = create_draft(zhangsan_client, flow["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200
    instance_id = draft["id"]
    task = find_assignment(lisi_client, instance_id)

    no_opinion = act(lisi_client, task["assignment_id"], opinion="")
    assert no_opinion.status_code == 422, no_opinion.text

    no_attachment = act(lisi_client, task["assignment_id"], opinion="同意但没附件")
    assert no_attachment.status_code == 422, no_attachment.text

    uploaded = upload_file(lisi_client, filename="opinion.txt", content=b"ok")
    assert uploaded.status_code in (200, 201), uploaded.text
    attachment_id = uploaded.json()["id"]

    approved = act(
        lisi_client,
        task["assignment_id"],
        opinion="同意并附说明",
        attachment_ids=[attachment_id],
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"


def test_notification_flow(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    def unread(client: ApiClient) -> int:
        response = client.get("notifications/unread-count")
        assert response.status_code == 200, response.text
        return response.json()["count"]

    baseline = unread(lisi_client)
    data = leave_data(reason="NOTIFY-01 通知闭环")
    draft = create_draft(zhangsan_client, seed["leave_flow"]["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200
    instance_id = draft["id"]

    after_submit = unread(lisi_client)
    assert after_submit > baseline

    items = lisi_client.get("notifications?size=100").json()["items"]
    unread_items = [item for item in items if not item["is_read"]]
    assert unread_items
    marked = lisi_client.post(f"notifications/{unread_items[0]['id']}/read")
    assert marked.status_code == 200, marked.text
    assert unread(lisi_client) == after_submit - 1

    task = find_assignment(lisi_client, instance_id)
    assert act(lisi_client, task["assignment_id"], opinion="同意").status_code == 200

    zhang_before = unread(zhangsan_client)
    assert zhang_before > 0
    assert zhangsan_client.post("notifications/read-all").status_code == 200
    assert unread(zhangsan_client) == 0


def _has_notification(client: ApiClient, instance_id: int, type_: str) -> bool:
    items = client.get("notifications?size=100").json()["items"]
    return any(
        item["type"] == type_
        and (item.get("payload") or {}).get("instance_id") == instance_id
        for item in items
    )


def test_reject_cancel_and_cc_notifications(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    # 驳回通知
    data = leave_data(reason="NOTIFY 驳回")
    draft = create_draft(zhangsan_client, seed["leave_flow"]["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200
    task = find_assignment(lisi_client, draft["id"])
    assert act(lisi_client, task["assignment_id"], action="REJECT", opinion="驳回").status_code == 200
    assert _has_notification(zhangsan_client, draft["id"], "INSTANCE_REJECTED")

    # 或签取消通知
    form = create_form_and_publish(admin_client, name="E2E 取消通知表单")
    any_flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 取消通知流程",
        definition=parallel_any_definition(
            [seed["users"]["lisi"]["id"], seed["users"]["wangwu"]["id"]]
        ),
    )
    any_data = {"reason": "NOTIFY 取消"}
    any_draft = create_draft(zhangsan_client, any_flow["id"], any_data)
    assert submit(zhangsan_client, any_draft["id"], any_data).status_code == 200
    lisi_task = find_assignment(lisi_client, any_draft["id"])
    assert act(lisi_client, lisi_task["assignment_id"], opinion="同意").status_code == 200
    assert _has_notification(wangwu_client, any_draft["id"], "TASK_CANCELLED")

    # 抄送通知
    reimburse_id = approve_reimburse(
        zhangsan=zhangsan_client,
        lisi=lisi_client,
        wangwu=wangwu_client,
        admin=admin_client,
        flow_id=seed["reimburse_flow"]["id"],
        reason="NOTIFY 抄送",
    )
    assert _has_notification(wangwu_client, reimburse_id, "CC_RECEIVED")


def test_dashboard_personal_and_admin_counts(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    for index in range(2):
        data = leave_data(reason=f"DASH-01 {index}")
        draft = create_draft(zhangsan_client, seed["leave_flow"]["id"], data)
        assert submit(zhangsan_client, draft["id"], data).status_code == 200

    zhang = zhangsan_client.get("dashboard/overview").json()
    assert zhang["admin"] is None
    assert zhang["personal"]["mine_running"] >= 2

    lisi = lisi_client.get("dashboard/overview").json()
    assert lisi["personal"]["todo"] >= 2

    admin = admin_client.get("dashboard/overview").json()
    assert admin["admin"]["running"] >= 2
    assert admin["admin"]["pending_backlog"] >= 2
