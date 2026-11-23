from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    create_draft,
    create_form_and_publish,
    find_assignment,
    leave_data,
    simple_form_schema,
    submit,
)


def test_idor_on_tasks_templates_admin_and_snapshot(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
    outsider: tuple[ApiClient, dict[str, Any]],
) -> None:
    outsider_client, _ = outsider
    data = leave_data(reason="SEC-01 IDOR")
    draft = create_draft(zhangsan_client, seed["leave_flow"]["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200
    instance_id = draft["id"]
    task = find_assignment(lisi_client, instance_id)

    for path in (
        f"tasks/assignments/{task['assignment_id']}",
        f"tasks/assignments/{task['assignment_id']}/return-targets",
        "form-templates",
        "flow-templates",
        "admin/audit-logs",
    ):
        response = outsider_client.get(path)
        assert response.status_code in (403, 404), f"{path}: {response.status_code} {response.text}"

    terminate = outsider_client.post(
        f"instances/{instance_id}/terminate", json={"reason": "越权终止"}
    )
    assert terminate.status_code in (403, 404), terminate.text

    timeline = zhangsan_client.get(f"instances/{instance_id}/timeline").json()
    snapshot_id = next(item["snapshot_id"] for item in timeline if item.get("snapshot_id"))
    snapshot = outsider_client.get(
        f"instances/{instance_id}/snapshots/{snapshot_id}"
    )
    assert snapshot.status_code in (403, 404), snapshot.text


def test_rich_text_rejects_raw_html(admin_client: ApiClient) -> None:
    schema = simple_form_schema()
    schema["sections"][0]["fields"].append(
        {
            "key": "danger",
            "label": "危险说明",
            "type": "rich_text",
            "sort": 9,
            "display": {"markdown": "<script>alert(1)</script>"},
        }
    )
    form = admin_client.post(
        "form-templates",
        json={"name": "E2E XSS 表单", "schema_data": schema},
    )
    assert form.status_code in (200, 201), form.text
    form_id = form.json()["id"]
    versions = admin_client.get(f"form-templates/{form_id}/versions").json()
    draft = next(item for item in versions if item["status"] == "DRAFT")
    published = admin_client.post(
        f"form-versions/{draft['id']}/publish", json={"remark": "E2E XSS"}
    )
    assert published.status_code == 422, published.text
    codes = {
        issue["code"]
        for issue in published.json()["detail"].get("extra", {}).get("errors", [])
    }
    assert "DISPLAY_RAW_HTML" in codes
