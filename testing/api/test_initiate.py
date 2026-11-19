from __future__ import annotations

import uuid
from typing import Any

from support.client import ApiClient
from support.factories import (
    create_draft,
    leave_data,
    submit,
    todo,
    update_draft,
)


def _field_keys(options: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for section in options.get("schema_data", {}).get("sections", []):
        for field in section.get("fields", []):
            keys.add(field["key"])
            for column in field.get("columns", []):
                keys.add(f"{field['key']}[].{column['key']}")
    return keys


def test_available_flows_and_leave_start_options(
    zhangsan_client: ApiClient, seed: dict[str, Any]
) -> None:
    response = zhangsan_client.get("instances/available-flows")
    assert response.status_code == 200, response.text
    codes = {flow["code"] for flow in response.json()}
    assert {"SAMPLE_LEAVE_FLOW", "SAMPLE_REIMBURSE_FLOW"} <= codes

    options = zhangsan_client.get(
        f"instances/start-options/{seed['leave_flow']['id']}"
    )
    assert options.status_code == 200, options.text
    body = options.json()
    keys = _field_keys(body)
    assert {"leaveType", "startDate", "endDate", "days", "reason"} <= keys
    assert body["permissions"]["leaveType"]["visible"] is True
    assert body["permissions"]["leaveType"]["editable"] is True
    assert body["permissions"]["days"]["editable"] is False
    assert body["flow_version_id"] == seed["leave_flow"]["current_version_id"]


def test_reimburse_start_options_does_not_expose_hidden_keys(
    zhangsan_client: ApiClient, seed: dict[str, Any]
) -> None:
    response = zhangsan_client.get(
        f"instances/start-options/{seed['reimburse_flow']['id']}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    keys = _field_keys(body)
    permissions = body.get("permissions", {})

    # D-04：hidden 字段的 key/标签不应下发给无权限视角。
    assert "actualAmount" not in keys
    assert "invoiceNo" not in keys
    assert "actualAmount" not in permissions
    assert "invoiceNo" not in permissions


def test_draft_update_submit_and_double_submit(
    zhangsan_client: ApiClient, lisi_client: ApiClient, seed: dict[str, Any]
) -> None:
    data = leave_data(reason="INIT-02/03 草稿与幂等")
    draft = create_draft(zhangsan_client, seed["leave_flow"]["id"], data)
    assert draft["status"] == "DRAFT"
    assert draft["code"]
    assert draft["title"]

    updated = update_draft(
        zhangsan_client,
        draft["id"],
        {**data, "reason": "INIT-02 自动暂存后提交"},
    )
    assert updated["status"] == "DRAFT"

    request_id = uuid.uuid4().hex
    submitted = submit(
        zhangsan_client,
        draft["id"],
        {**data, "reason": "INIT-02 自动暂存后提交"},
        request_id=request_id,
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["status"] == "RUNNING"

    tasks = [item for item in todo(lisi_client) if item["instance_id"] == draft["id"]]
    assert len(tasks) == 1

    replay = submit(
        zhangsan_client,
        draft["id"],
        {**data, "reason": "INIT-02 自动暂存后提交"},
        request_id=request_id,
    )
    assert replay.status_code in (200, 409, 422), replay.text
    tasks_after = [item for item in todo(lisi_client) if item["instance_id"] == draft["id"]]
    assert len(tasks_after) == 1, "重复提交不得产生第二条任务"


def test_submit_rejects_missing_required_fields(
    zhangsan_client: ApiClient, lisi_client: ApiClient, seed: dict[str, Any]
) -> None:
    draft = create_draft(
        zhangsan_client,
        seed["leave_flow"]["id"],
        {"leaveType": "personal"},
    )
    response = submit(zhangsan_client, draft["id"], {"leaveType": "personal"})
    assert response.status_code in (400, 422), response.text
    tasks = [item for item in todo(lisi_client) if item["instance_id"] == draft["id"]]
    assert tasks == []
