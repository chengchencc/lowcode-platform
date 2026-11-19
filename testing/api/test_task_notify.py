from __future__ import annotations

from support.client import ApiClient
from support.factories import (
    act,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    find_assignment,
    leave_data,
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
