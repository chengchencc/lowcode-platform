from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    act,
    attachment_form_schema,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    download_file,
    fill_then_approval_attachment_definition,
    find_assignment,
    render,
    simple_data,
    submit,
    upload_file,
)


def test_hidden_attachment_field_visibility_and_download(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(
        admin_client, name="E2E 隐藏附件表单", schema=attachment_form_schema()
    )
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 隐藏附件流程",
        definition=fill_then_approval_attachment_definition(
            fill_user_id=seed["users"]["wangwu"]["id"],
            approver_user_id=seed["users"]["lisi"]["id"],
        ),
    )

    data = simple_data(reason="PERM-04 隐藏附件")
    draft = create_draft(zhangsan_client, flow["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text
    instance_id = draft["id"]

    uploaded = upload_file(
        wangwu_client, filename="hidden-secret.pdf", content=b"hidden-file"
    )
    assert uploaded.status_code in (200, 201), uploaded.text
    attachment_id = uploaded.json()["id"]

    fill_task = find_assignment(wangwu_client, instance_id)
    filled = act(
        wangwu_client,
        fill_task["assignment_id"],
        action="SUBMIT",
        opinion="附件已补",
        field_patch={"secret_file": [attachment_id]},
    )
    assert filled.status_code == 200, filled.text
    assert filled.json()["status"] == "RUNNING"

    # 发起人运行中：字段 key、值、附件元数据、下载都不可见
    running = render(zhangsan_client, instance_id)
    assert running.status_code == 200, running.text
    body = running.json()
    schema_keys = [
        field["key"]
        for section in body["schema_data"]["sections"]
        for field in section["fields"]
    ]
    assert "secret_file" not in schema_keys
    assert "secret_file" not in body["permissions"]
    assert "secret_file" not in body["values"]
    attachment_names = {item["file_name"] for item in body["attachments"]}
    assert "hidden-secret.pdf" not in attachment_names
    assert download_file(zhangsan_client, attachment_id).status_code in (403, 404)

    # 审批人节点开放：可看元数据、可下载
    approver = render(lisi_client, instance_id).json()
    assert "secret_file" in approver["permissions"]
    assert "hidden-secret.pdf" in {item["file_name"] for item in approver["attachments"]}
    assert download_file(lisi_client, attachment_id).status_code == 200

    # 终态归档：发起人也可看/可下载
    approval = find_assignment(lisi_client, instance_id)
    assert act(lisi_client, approval["assignment_id"], opinion="通过").status_code == 200
    archived = render(zhangsan_client, instance_id).json()
    assert "secret_file" in archived["permissions"]
    assert "hidden-secret.pdf" in {item["file_name"] for item in archived["attachments"]}
    assert download_file(zhangsan_client, attachment_id).status_code == 200
