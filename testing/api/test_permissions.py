from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    act,
    create_draft,
    find_assignment,
    leave_data,
    reimburse_data,
    render,
    submit,
)


def _field_keys(body: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for section in body.get("schema_data", {}).get("sections", []):
        for field in section.get("fields", []):
            keys.add(field["key"])
            for column in field.get("columns", []):
                keys.add(f"{field['key']}[].{column['key']}")
    return keys


def _submit_leave(client: ApiClient, flow_id: int, reason: str) -> int:
    data = leave_data(reason=reason)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def test_outsider_cannot_access_instance(
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
    outsider: tuple[ApiClient, dict[str, Any]],
) -> None:
    outsider_client, _ = outsider
    instance_id = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "PERM-03 无关用户")

    for path in (
        f"instances/{instance_id}/render",
        f"instances/{instance_id}/timeline",
        f"instances/{instance_id}/export",
    ):
        response = outsider_client.get(path)
        assert response.status_code in (403, 404), f"{path}: {response.status_code} {response.text}"
        assert "请假申请" not in response.text


def test_designer_cannot_access_unrelated_instance_or_admin(
    zhangsan_client: ApiClient,
    zhaoliu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "PERM-03 设计者")

    for path in (
        f"instances/{instance_id}/render",
        f"instances/{instance_id}/timeline",
        "admin/instances",
        "admin/audit-logs",
        "instances/archive",
    ):
        response = zhaoliu_client.get(path)
        assert response.status_code in (403, 404), f"{path}: {response.status_code} {response.text}"


def test_designer_dashboard_has_no_admin_block(zhaoliu_client: ApiClient) -> None:
    response = zhaoliu_client.get("dashboard/overview")
    assert response.status_code == 200, response.text
    # D-02：设计者只看个人工作台，不返回管理员全局概览。
    assert response.json().get("admin") is None


def test_hidden_keys_should_not_be_in_running_render(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    data = reimburse_data(amount=2500, reason="PERM-02 hidden key")
    draft = create_draft(zhangsan_client, seed["reimburse_flow"]["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text

    manager_task = find_assignment(lisi_client, draft["id"])
    assert act(lisi_client, manager_task["assignment_id"], opinion="同意").status_code == 200

    body = render(zhangsan_client, draft["id"]).json()
    keys = _field_keys(body)
    permissions = body.get("permissions", {})

    # D-04：运行中无权限视角不应拿到 hidden 字段的 key/标签/值。
    assert "actualAmount" not in keys
    assert "invoiceNo" not in keys
    assert "actualAmount" not in permissions
    assert "invoiceNo" not in permissions
    values = body.get("values") or {}
    assert "actualAmount" not in values
    assert "invoiceNo" not in values


def test_hidden_values_visible_after_archive(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    data = reimburse_data(amount=2500, reason="PERM-02 归档可见")
    draft = create_draft(zhangsan_client, seed["reimburse_flow"]["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text
    instance_id = draft["id"]

    manager_task = find_assignment(lisi_client, instance_id)
    assert act(lisi_client, manager_task["assignment_id"], opinion="同意").status_code == 200

    before = render(zhangsan_client, instance_id).json()
    before_values = before.get("values") or {}
    assert "actualAmount" not in before_values
    assert "invoiceNo" not in before_values

    finance_task = find_assignment(wangwu_client, instance_id)
    admin_task = find_assignment(admin_client, instance_id)
    assert act(wangwu_client, finance_task["assignment_id"], opinion="同意").status_code == 200
    assert act(admin_client, admin_task["assignment_id"], opinion="同意").status_code == 200

    fill_task = find_assignment(wangwu_client, instance_id, node_type="FILL")
    filled = act(
        wangwu_client,
        fill_task["assignment_id"],
        action="SUBMIT",
        opinion="核销完成",
        field_patch={"actualAmount": 2500, "invoiceNo": "INV-E2E-002"},
    )
    assert filled.status_code == 200, filled.text
    assert filled.json()["status"] == "APPROVED"

    after = render(zhangsan_client, instance_id).json()
    after_values = after.get("values") or {}
    # 终态归档视角：发起人可见补充字段（只读）。
    assert after_values.get("actualAmount") == 2500
    assert after_values.get("invoiceNo") == "INV-E2E-002"
