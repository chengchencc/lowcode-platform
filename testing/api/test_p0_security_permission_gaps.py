"""P0 补齐：导出/快照/任务 IDOR、上传边界、分区与条件权限。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from support.client import ApiClient
from support.factories import (
    _approval_node,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    find_assignment,
    leave_data,
    render,
    simple_data,
    submit,
    upload_file,
    user_rule,
)

STORAGE_ROOT = Path(__file__).resolve().parents[2] / "testing/.runtime/e2e/storage"


def _submit(client: ApiClient, flow_id: int, data: dict[str, Any]) -> int:
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def test_export_snapshot_and_task_idor(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
    outsider: tuple[ApiClient, dict[str, Any]],
) -> None:
    outsider_client, _ = outsider
    data = leave_data(reason="SEC-01 导出与快照")
    draft = create_draft(zhangsan_client, seed["leave_flow"]["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200
    instance_id = draft["id"]
    assignment = find_assignment(lisi_client, instance_id, node_type=None)

    for path in (
        f"instances/{instance_id}/export",
        f"instances/{instance_id}/timeline",
        f"instances/{instance_id}/progress",
        "instances/archive/export",
        "instances/archive",
    ):
        response = outsider_client.get(path)
        assert response.status_code in (403, 404), f"{path}: {response.status_code} {response.text}"

    act_response = outsider_client.post(
        f"tasks/assignments/{assignment['assignment_id']}/act",
        json={
            "action": "AGREE",
            "opinion": "越权处理",
            "attachment_ids": [],
            "field_patch": {},
            "return_target": None,
        },
    )
    assert act_response.status_code in (403, 404), act_response.text

    timeline = zhangsan_client.get(f"instances/{instance_id}/timeline").json()
    snapshot_ids = [item["snapshot_id"] for item in timeline if item.get("snapshot_id")]
    assert len(snapshot_ids) >= 1
    if len(snapshot_ids) >= 2:
        diff = outsider_client.get(
            f"instances/{instance_id}/snapshots/diff",
            params={"from": snapshot_ids[0], "to": snapshot_ids[-1]},
        )
        assert diff.status_code in (403, 404), diff.text

    # 普通用户不能导出整个归档
    archive_export = zhangsan_client.get("instances/archive/export")
    assert archive_export.status_code in (403, 404), archive_export.text


def test_upload_path_traversal_and_size_limit(zhangsan_client: ApiClient) -> None:
    traversal = upload_file(
        zhangsan_client,
        filename="../../evil.txt",
        content=b"path traversal probe",
    )
    assert traversal.status_code in (200, 201), traversal.text
    body = traversal.json()

    downloaded = zhangsan_client.get(f"files/{body['id']}/download")
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == b"path traversal probe"

    # 存储名必须是 UUID，原始文件名只作为展示字段保留
    stored = list(STORAGE_ROOT.rglob("*"))
    assert stored, "附件目录为空"
    assert not any("evil" in path.name for path in stored if path.is_file())

    oversized = upload_file(
        zhangsan_client,
        filename="too-large.txt",
        content=b"x" * (21 * 1024 * 1024),
    )
    assert oversized.status_code in (400, 413, 422), oversized.text


def test_partition_and_conditional_permissions(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    schema = {
        "model_version": 1,
        "title_field": "reason",
        "sections": [
            {
                "key": "sec_apply",
                "title": "申请",
                "stage": "apply",
                "fields": [
                    {"key": "reason", "label": "事由", "type": "text", "required": True},
                    {"key": "amount", "label": "金额", "type": "number"},
                ],
            },
            {
                "key": "sec_supplement",
                "title": "补充",
                "stage": "supplement",
                "fields": [
                    {
                        "key": "actualAmount",
                        "label": "实际金额",
                        "type": "number",
                        "visible_at_start": False,
                    }
                ],
            },
        ],
    }
    form = create_form_and_publish(admin_client, name="E2E 分区条件权限表单", schema=schema)
    node = _approval_node("a1", "审批", user_rule(seed["users"]["lisi"]["id"]))
    node["fields_permission"] = {
        "base": "readonly",
        "partitions": {"sec_supplement": "editable"},
        "overrides": {},
        "conditional_overrides": [
            {
                "when": {
                    "op": "and",
                    "conditions": [{"field": "amount", "cmp": ">", "value": 100}],
                },
                "field_key": "reason",
                "mode": "hidden",
            }
        ],
    }
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 分区条件权限流程",
        definition={"steps": [node]},
    )

    hit = _submit(zhangsan_client, flow["id"], {"reason": "命中条件", "amount": 500})
    hit_assignment = find_assignment(lisi_client, hit)
    rendered_hit = render(
        lisi_client, hit, assignment_id=hit_assignment["assignment_id"]
    ).json()
    # D-04：隐藏字段的 key/值都不下发
    assert "reason" not in rendered_hit["permissions"]
    assert "reason" not in rendered_hit["values"]
    assert rendered_hit["permissions"]["actualAmount"]["visible"] is True
    assert rendered_hit["permissions"]["actualAmount"]["editable"] is True

    miss = _submit(zhangsan_client, flow["id"], {"reason": "未命中条件", "amount": 50})
    miss_assignment = find_assignment(lisi_client, miss)
    rendered_miss = render(
        lisi_client, miss, assignment_id=miss_assignment["assignment_id"]
    ).json()
    assert rendered_miss["permissions"]["reason"]["visible"] is True
    assert rendered_miss["values"]["reason"] == "未命中条件"
    assert rendered_miss["permissions"]["actualAmount"]["editable"] is True
