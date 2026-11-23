from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    act,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    fill_then_approval_definition,
    find_assignment,
    hidden_form_schema,
    simple_data,
    submit,
)


def test_running_snapshot_hides_supplement_from_initiator(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(
        admin_client, name="E2E 快照裁剪表单", schema=hidden_form_schema()
    )
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 快照裁剪流程",
        definition=fill_then_approval_definition(
            fill_user_id=seed["users"]["wangwu"]["id"],
            approver_user_id=seed["users"]["lisi"]["id"],
        ),
    )

    data = simple_data(reason="PERM-02 快照裁剪")
    draft = create_draft(zhangsan_client, flow["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text
    instance_id = draft["id"]

    fill_task = find_assignment(wangwu_client, instance_id)
    filled = act(
        wangwu_client,
        fill_task["assignment_id"],
        action="SUBMIT",
        opinion="补充完成",
        field_patch={"secret": "TOP-SECRET-001"},
    )
    assert filled.status_code == 200, filled.text
    assert filled.json()["status"] == "RUNNING"
    assert find_assignment(lisi_client, instance_id)

    timeline = zhangsan_client.get(f"instances/{instance_id}/timeline").json()
    actions = [a for a in timeline if a.get("snapshot_id")]
    submit_snapshot = next(
        a for a in actions if a["action"] == "SUBMIT" and a["node_key"] is None
    )
    fill_snapshot = next(a for a in actions if a["action"] == "SUBMIT" and a["node_key"] == "f1")

    # 1) 详情快照视图（前端实际使用的 render?snapshot_id）
    snapshot_render = zhangsan_client.get(
        f"instances/{instance_id}/render", params={"snapshot_id": fill_snapshot["snapshot_id"]}
    )
    assert snapshot_render.status_code == 200, snapshot_render.text
    body = snapshot_render.json()
    assert "TOP-SECRET-001" not in snapshot_render.text
    assert "secret" not in (body.get("values") or {})
    assert "secret" not in (body.get("permissions") or {})
    schema_keys = [
        field["key"]
        for section in (body.get("schema_data") or {}).get("sections", [])
        for field in section.get("fields", [])
    ]
    assert "secret" not in schema_keys

    # 2) 独立快照接口
    separate = zhangsan_client.get(
        f"instances/{instance_id}/snapshots/{fill_snapshot['snapshot_id']}"
    )
    assert separate.status_code == 200, separate.text
    assert "TOP-SECRET-001" not in separate.text
    assert "secret" not in separate.text

    # 3) 快照对照
    diff = zhangsan_client.get(
        f"instances/{instance_id}/snapshots/diff",
        params={"from": submit_snapshot["snapshot_id"], "to": fill_snapshot["snapshot_id"]},
    )
    assert diff.status_code == 200, diff.text
    assert "TOP-SECRET-001" not in diff.text
    assert "secret" not in diff.text

    # 4) 通过后终态归档视角可见
    approval = find_assignment(lisi_client, instance_id)
    assert act(lisi_client, approval["assignment_id"], opinion="复核通过").status_code == 200
    archived = zhangsan_client.get(
        f"instances/{instance_id}/render", params={"snapshot_id": fill_snapshot["snapshot_id"]}
    )
    assert archived.status_code == 200, archived.text
    assert "TOP-SECRET-001" in archived.text
