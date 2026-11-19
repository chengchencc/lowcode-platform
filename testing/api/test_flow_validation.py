from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    create_form_and_publish,
    sequential_definition,
)


def _flow_draft(admin: ApiClient, form_id: int, name: str) -> tuple[dict[str, Any], int]:
    response = admin.post(
        "flow-templates",
        json={
            "name": name,
            "form_template_id": form_id,
            "initiator_scope": {"type": "all"},
        },
    )
    assert response.status_code in (200, 201), response.text
    flow = response.json()
    versions = admin.get(f"flow-templates/{flow['id']}/versions")
    assert versions.status_code == 200, versions.text
    draft = next(v for v in versions.json() if v["status"] == "DRAFT")
    return flow, draft["id"]


def _publish_with(admin: ApiClient, version_id: int, definition: dict[str, Any]) -> Any:
    saved = admin.put(f"flow-versions/{version_id}", json={"definition": definition})
    assert saved.status_code == 200, saved.text
    return admin.post(f"flow-versions/{version_id}/publish", json={"remark": "E2E 校验"})


def test_publish_rejects_node_without_approver(
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 无审批人表单")
    flow, version_id = _flow_draft(admin_client, form["id"], "E2E 无审批人流程")
    definition = sequential_definition(
        [("a1", "无审批人节点", seed["users"]["lisi"]["id"])]
    )
    definition["steps"][0]["assignee"] = {
        "mode": "SINGLE",
        "sources": [],
        "on_empty": "to_admin",
        "initiator_select": None,
    }
    published = _publish_with(admin_client, version_id, definition)
    assert published.status_code == 422, published.text
    assert published.json()["detail"]["code"] == "FLOW_INVALID"
    detail = admin_client.get(f"flow-templates/{flow['id']}").json()
    assert detail["status"] != "PUBLISHED"
