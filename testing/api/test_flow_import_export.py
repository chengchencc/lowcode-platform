"""流程配置导出 / 导入（F2.9）。

跨环境迁移时：在源环境导出 JSON，到目标环境选择一个已发布表单后导入，
导入结果始终是草稿；组织引用（角色/部门/人员 id）原样保留，由用户在设计器里
按目标环境重新梳理后再发布。
"""

from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    create_flow_and_publish,
    create_form_and_publish,
    sequential_definition,
    unique,
)


def test_flow_export_import_roundtrip(
    admin_client: ApiClient, seed: dict[str, Any]
) -> None:
    form = create_form_and_publish(admin_client, name=unique("E2E 迁移表单"))
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name=unique("E2E 迁移流程"),
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
        initiator_scope={
            "type": "role",
            "role_ids": [seed["roles"]["designer"]["id"]],
        },
    )

    exported = admin_client.get(f"flow-templates/{flow['id']}/export")
    assert exported.status_code == 200, exported.text
    payload = exported.json()
    assert payload["name"] == flow["name"]
    assert payload["form_name"] == form["name"]
    assert payload["form_code"] == form["code"]
    assert payload["initiator_scope"]["type"] == "role"
    assert payload["definition"]["steps"][0]["id"] == "a1"

    imported = admin_client.post(
        "flow-templates/import",
        json={
            **payload,
            "name": f"{payload['name']}（导入）",
            "code": None,
            "form_template_id": form["id"],
        },
    )
    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["status"] == "DRAFT"
    assert body["form_template_id"] == form["id"]
    assert body["current_version_id"] is None
    assert body["draft_version_id"] is not None

    version = admin_client.get(f"flow-versions/{body['draft_version_id']}").json()
    assert version["status"] == "DRAFT"
    assert version["definition"] == payload["definition"]

    validated = admin_client.post(
        f"flow-versions/{body['draft_version_id']}/validate"
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["valid"] is True, validated.json()

    published = admin_client.post(
        f"flow-versions/{body['draft_version_id']}/publish",
        json={"remark": "E2E 导入后发布"},
    )
    assert published.status_code == 200, published.text
    assert published.json()["locked_form_version_no"] == 1


def test_import_requires_designer(zhangsan_client: ApiClient) -> None:
    assert zhangsan_client.get("flow-templates/1/export").status_code == 403
    assert (
        zhangsan_client.post(
            "flow-templates/import",
            json={"form_template_id": 1, "definition": {"steps": []}},
        ).status_code
        == 403
    )
