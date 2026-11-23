from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    create_draft,
    create_form_and_publish,
    find_assignment,
    sequential_definition,
    simple_data,
    submit,
)


def test_hundred_node_flow_has_defined_behavior(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 百节点表单")
    approvals = [
        (f"a{index}", f"审批{index}", seed["users"]["lisi"]["id"])
        for index in range(1, 101)
    ]
    definition = sequential_definition(approvals)

    created = admin_client.post(
        "flow-templates",
        json={
            "name": "E2E 百节点流程",
            "form_template_id": form["id"],
            "initiator_scope": {"type": "all"},
        },
    )
    assert created.status_code in (200, 201), created.text
    flow = created.json()
    versions = admin_client.get(f"flow-templates/{flow['id']}/versions").json()
    version_id = next(item["id"] for item in versions if item["status"] == "DRAFT")
    saved = admin_client.put(
        f"flow-versions/{version_id}", json={"definition": definition}
    )
    assert saved.status_code == 200, saved.text

    published = admin_client.post(
        f"flow-versions/{version_id}/publish", json={"remark": "E2E 百节点"}
    )
    # 允许发布或明确拒绝（4xx），不允许 500
    assert published.status_code in (200, 422), published.text
    if published.status_code != 200:
        return

    data = simple_data(reason="FLOW-03 百节点")
    draft = create_draft(zhangsan_client, flow["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text
    task = find_assignment(lisi_client, draft["id"])
    assert task["node_key"] == "a1"


def test_duplicate_node_names_have_defined_behavior(
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 重名节点表单")
    definition = sequential_definition(
        [
            ("a1", "同名审批", seed["users"]["lisi"]["id"]),
            ("a2", "同名审批", seed["users"]["wangwu"]["id"]),
        ]
    )
    created = admin_client.post(
        "flow-templates",
        json={
            "name": "E2E 重名节点流程",
            "form_template_id": form["id"],
            "initiator_scope": {"type": "all"},
        },
    )
    assert created.status_code in (200, 201), created.text
    flow = created.json()
    versions = admin_client.get(f"flow-templates/{flow['id']}/versions").json()
    version_id = next(item["id"] for item in versions if item["status"] == "DRAFT")
    assert admin_client.put(
        f"flow-versions/{version_id}", json={"definition": definition}
    ).status_code == 200
    published = admin_client.post(
        f"flow-versions/{version_id}/publish", json={"remark": "E2E 重名"}
    )
    assert published.status_code in (200, 422), published.text
