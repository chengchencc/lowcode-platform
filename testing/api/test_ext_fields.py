from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    act,
    archive_export,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    find_assignment,
    render,
    sequential_definition,
    simple_data,
    submit,
)


def _add_field(admin: ApiClient, instance_id: int, label: str = "合同编号") -> str:
    response = admin.post(
        f"instances/{instance_id}/ext-fields",
        json={"label": label, "type": "text", "required": True},
    )
    assert response.status_code == 200, response.text
    return response.json()["ext_fields"][0]["field_key"]


def test_ext_field_visibility_editability_and_archive(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 扩展字段表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 扩展字段流程",
        definition=sequential_definition(
            [
                ("a1", "一级审批", seed["users"]["lisi"]["id"]),
                ("a2", "二级审批", seed["users"]["wangwu"]["id"]),
            ]
        ),
    )

    data = simple_data(reason="EXT-01 运行中追加字段")
    draft = create_draft(zhangsan_client, flow["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200
    instance_id = draft["id"]

    first_task = find_assignment(lisi_client, instance_id)
    ext_key = _add_field(admin_client, instance_id)

    # 发起人运行中不可见
    zhang_running = render(zhangsan_client, instance_id).json()
    assert ext_key not in zhang_running["permissions"]
    assert ext_key not in zhang_running["values"]

    # 当前节点可见、可编辑、必填
    handler = render(
        lisi_client, instance_id, assignment_id=first_task["assignment_id"]
    ).json()
    assert handler["permissions"][ext_key]["visible"] is True
    assert handler["permissions"][ext_key]["editable"] is True
    assert handler["permissions"][ext_key]["required"] is True

    missing = act(lisi_client, first_task["assignment_id"], opinion="没填扩展字段")
    assert missing.status_code == 422, missing.text

    assert act(
        lisi_client,
        first_task["assignment_id"],
        opinion="填了扩展字段",
        field_patch={ext_key: "HT-001"},
    ).status_code == 200

    # 后续节点：可见只读
    second_task = find_assignment(wangwu_client, instance_id)
    second = render(
        wangwu_client, instance_id, assignment_id=second_task["assignment_id"]
    ).json()
    assert second["permissions"][ext_key]["visible"] is True
    assert second["permissions"][ext_key]["editable"] is False
    assert second["values"][ext_key] == "HT-001"

    assert act(wangwu_client, second_task["assignment_id"], opinion="通过").status_code == 200
    final = render(zhangsan_client, instance_id).json()
    assert final["instance"]["status"] == "APPROVED"
    assert final["permissions"][ext_key]["visible"] is True
    assert final["values"][ext_key] == "HT-001"

    exported = archive_export(
        admin_client, {"flow_template_id": flow["id"]}
    )
    assert exported.status_code == 200, exported.text
    text = exported.content.decode("utf-8-sig", errors="replace")
    assert "合同编号" in text and "HT-001" in text

    # 终态不能再追加
    late = admin_client.post(
        f"instances/{instance_id}/ext-fields",
        json={"label": "迟到字段", "type": "text"},
    )
    assert late.status_code == 422, late.text

    # 非设计者不能追加
    forbidden = zhangsan_client.post(
        f"instances/{instance_id}/ext-fields",
        json={"label": "越权字段", "type": "text"},
    )
    assert forbidden.status_code in (403, 404), forbidden.text


def test_disable_ext_field_hides_it(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 停用扩展字段表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 停用扩展字段流程",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
    )
    data = simple_data(reason="EXT-01 停用字段")
    draft = create_draft(zhangsan_client, flow["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200
    instance_id = draft["id"]

    ext_key = _add_field(admin_client, instance_id, "临时字段")
    disabled = admin_client.post(
        f"instances/{instance_id}/ext-fields/{ext_key}/disable"
    )
    assert disabled.status_code == 200, disabled.text

    handler = render(lisi_client, instance_id).json()
    assert ext_key not in handler["permissions"]
    assert ext_key not in handler["values"]
