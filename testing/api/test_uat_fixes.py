"""UAT 反馈的回归：退回目标为空、撤回/驳回复制为新申请。"""

from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    act,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    find_assignment,
    render,
    sequential_definition,
    simple_data,
    submit,
    withdraw,
)


def _submit(client: ApiClient, flow_id: int, data: dict[str, Any]) -> int:
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def test_return_action_hidden_when_no_previous_approver(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="UAT 退回目标表单")
    single = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="UAT 单节点流程",
        definition=sequential_definition([("a1", "审批", seed["users"]["lisi"]["id"])]),
    )
    data = simple_data(reason="UAT 退回目标")
    instance_id = _submit(zhangsan_client, single["id"], data)
    task = find_assignment(lisi_client, instance_id)
    rendered = render(
        lisi_client, instance_id, assignment_id=task["assignment_id"]
    ).json()
    assert "RETURN" not in rendered["allowed_actions"]
    assert rendered["return_targets"] == []

    # 有前序审批节点时仍应提供退回
    two = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="UAT 两节点流程",
        definition=sequential_definition(
            [
                ("a1", "初审", seed["users"]["lisi"]["id"]),
                ("a2", "复核", seed["users"]["wangwu"]["id"]),
            ]
        ),
    )
    instance_id2 = _submit(zhangsan_client, two["id"], data)
    first = find_assignment(lisi_client, instance_id2)
    assert act(lisi_client, first["assignment_id"], opinion="通过").status_code == 200
    second = find_assignment(wangwu_client, instance_id2)
    rendered2 = render(
        wangwu_client, instance_id2, assignment_id=second["assignment_id"]
    ).json()
    assert "RETURN" in rendered2["allowed_actions"]
    assert [item["node_id"] for item in rendered2["return_targets"]] == ["a1"]


def test_copy_withdrawn_and_rejected_to_new_draft(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    outsider: tuple[ApiClient, dict[str, Any]],
    seed: dict[str, Any],
) -> None:
    schema = {
        "model_version": 1,
        "title_field": "reason",
        "sections": [
            {
                "key": "sec",
                "title": "申请",
                "stage": "apply",
                "fields": [
                    {"key": "reason", "label": "事由", "type": "text", "required": True},
                    {
                        "key": "docNo",
                        "label": "表单编号",
                        "type": "text",
                        "auto_number": {"prefix": "CP", "seq_length": 3},
                    },
                ],
            }
        ],
    }
    form = create_form_and_publish(
        admin_client, name="UAT 复制申请表单", schema=schema
    )
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="UAT 复制申请流程",
        definition=sequential_definition([("a1", "审批", seed["users"]["lisi"]["id"])]),
    )

    withdrawn = _submit(
        zhangsan_client, flow["id"], {"reason": "撤回后复制", "docNo": "SHOULD-IGNORE"}
    )
    original = render(zhangsan_client, withdrawn).json()
    original_no = original["values"]["docNo"]
    assert withdraw(zhangsan_client, withdrawn, reason="不想要了").status_code == 200

    copied = zhangsan_client.post(f"instances/{withdrawn}/copy")
    assert copied.status_code == 201, copied.text
    body = copied.json()
    assert body["status"] == "DRAFT"
    assert body["id"] != withdrawn
    draft_values = render(zhangsan_client, body["id"]).json()["values"]
    assert draft_values["reason"] == "撤回后复制"
    assert draft_values["docNo"] != original_no
    assert draft_values["docNo"].startswith("CP")

    rejected = _submit(zhangsan_client, flow["id"], {"reason": "驳回后复制"})
    task = find_assignment(lisi_client, rejected)
    assert act(
        lisi_client, task["assignment_id"], action="REJECT", opinion="请修改"
    ).status_code == 200
    rejected_copy = zhangsan_client.post(f"instances/{rejected}/copy")
    assert rejected_copy.status_code == 201, rejected_copy.text
    assert rejected_copy.json()["status"] == "DRAFT"

    # 无关人员不可复制；运行中的实例也不可复制
    outsider_client, _ = outsider
    forbidden = outsider_client.post(f"instances/{rejected}/copy")
    assert forbidden.status_code in (403, 404), forbidden.text

    running = _submit(zhangsan_client, flow["id"], {"reason": "运行中"})
    invalid = zhangsan_client.post(f"instances/{running}/copy")
    assert invalid.status_code == 422, invalid.text

    # 管理员可以代复制（便于运维）
    admin_copy = admin_client.post(f"instances/{rejected}/copy")
    assert admin_copy.status_code == 201, admin_copy.text
