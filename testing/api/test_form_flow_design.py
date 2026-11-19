from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    act,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    find_assignment,
    hidden_form_schema,
    render,
    sequential_definition,
    simple_data,
    simple_form_schema,
    submit,
)


def _field_keys(schema: dict[str, Any]) -> set[str]:
    return {
        field["key"]
        for section in schema.get("sections", [])
        for field in section.get("fields", [])
    }


def _published_version(admin: ApiClient, form_id: int) -> dict[str, Any]:
    response = admin.get(f"form-templates/{form_id}/versions")
    assert response.status_code == 200, response.text
    return next(v for v in response.json() if v["status"] == "PUBLISHED")


def _add_and_publish_version(
    admin: ApiClient, form_id: int, schema: dict[str, Any]
) -> dict[str, Any]:
    created = admin.post(f"form-templates/{form_id}/versions", json={})
    assert created.status_code in (200, 201), created.text
    version_id = created.json()["id"]
    saved = admin.put(
        f"form-versions/{version_id}", json={"schema_data": schema}
    )
    assert saved.status_code == 200, saved.text
    published = admin.post(
        f"form-versions/{version_id}/publish", json={"remark": "E2E 新版本"}
    )
    assert published.status_code == 200, published.text
    return published.json()


def test_form_version_and_flow_lock(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 版本锁定表单")
    v1 = _published_version(admin_client, form["id"])

    flow1 = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 版本锁定流程一",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
    )
    flow1_detail = admin_client.get(f"flow-templates/{flow1['id']}").json()
    assert flow1_detail["locked_form_version_id"] == v1["id"]

    options1 = zhangsan_client.get(f"instances/start-options/{flow1['id']}")
    assert options1.status_code == 200, options1.text
    assert options1.json()["form_version_id"] == v1["id"]
    assert "note" not in _field_keys(options1.json()["schema_data"])

    # 表单发布新版本，但流程一未重新发布 → 仍锁旧版
    new_schema = simple_form_schema()
    new_schema["sections"][0]["fields"].append(
        {"key": "note", "label": "备注", "type": "text", "sort": 9,
         "required": False, "visible_at_start": True}
    )
    v2 = _add_and_publish_version(admin_client, form["id"], new_schema)
    assert v2["version_no"] == 2

    options1_again = zhangsan_client.get(f"instances/start-options/{flow1['id']}")
    assert options1_again.status_code == 200, options1_again.text
    assert options1_again.json()["form_version_id"] == v1["id"]
    assert "note" not in _field_keys(options1_again.json()["schema_data"])

    # 新流程发布 → 锁最新已发布版
    flow2 = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 版本锁定流程二",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
    )
    flow2_detail = admin_client.get(f"flow-templates/{flow2['id']}").json()
    assert flow2_detail["locked_form_version_id"] == v2["id"]
    options2 = zhangsan_client.get(f"instances/start-options/{flow2['id']}")
    assert options2.status_code == 200, options2.text
    assert options2.json()["form_version_id"] == v2["id"]
    assert "note" in _field_keys(options2.json()["schema_data"])


def test_server_side_validation_and_permission_matrix(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(
        admin_client, name="E2E 权限矩阵表单", schema=hidden_form_schema()
    )
    definition = sequential_definition(
        [("a1", "矩阵审批", seed["users"]["lisi"]["id"])]
    )
    definition["steps"][0]["fields_permission"] = {
        "base": "hidden",
        "partitions": {},
        "overrides": {"reason": "readonly", "amount": "editable-required"},
        "conditional_overrides": [],
    }
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 权限矩阵流程",
        definition=definition,
    )

    # 缺必填：服务端拒绝，不派任务
    missing_data = {"reason": ""}
    draft = create_draft(zhangsan_client, flow["id"], missing_data)
    missing = submit(zhangsan_client, draft["id"], missing_data)
    assert missing.status_code in (400, 422), missing.text

    # 正常提交，同时伪造 hidden 字段：服务端过滤
    data = {**simple_data(reason="原始事由", amount=100), "secret": "SHOULD-NOT-STORE"}
    draft = create_draft(zhangsan_client, flow["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text
    instance_id = draft["id"]

    task = find_assignment(lisi_client, instance_id)
    body = render(lisi_client, instance_id, assignment_id=task["assignment_id"]).json()
    assert body["permissions"]["reason"]["visible"] is True
    assert body["permissions"]["reason"]["editable"] is False
    assert body["permissions"]["amount"]["visible"] is True
    assert body["permissions"]["amount"]["editable"] is True
    assert body["permissions"]["amount"]["required"] is True
    assert "secret" not in body["permissions"]
    assert "secret" not in body["values"]

    # 处理时改只读/隐藏字段：不落库；可编辑字段正常落库
    approved = act(
        lisi_client,
        task["assignment_id"],
        opinion="矩阵审批",
        field_patch={"amount": 200, "reason": "篡改", "secret": "LEAK"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    final = render(zhangsan_client, instance_id).json()
    assert final["values"]["amount"] == 200
    assert final["values"]["reason"] == "原始事由"
    assert "secret" not in final["values"]
