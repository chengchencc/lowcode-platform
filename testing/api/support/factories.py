"""测试数据工厂与常用 API 动作。全部通过 HTTP。"""

from __future__ import annotations

import uuid
from typing import Any

from .client import ApiClient

TEST_PASSWORD = "testPass123"


def unique(prefix: str = "E2E") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def username(prefix: str = "e2e") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def create_user(
    admin: ApiClient,
    *,
    username_value: str,
    real_name: str = "E2E 用户",
    dept_id: int | None = None,
    role_ids: list[int] | None = None,
    password: str = TEST_PASSWORD,
) -> dict[str, Any]:
    response = admin.post(
        "users",
        json={
            "username": username_value,
            "password": password,
            "real_name": real_name,
            "dept_id": dept_id,
            "role_ids": role_ids or [],
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def create_dept(
    admin: ApiClient,
    *,
    name: str,
    code: str,
    parent_id: int | None = None,
    manager_user_id: int | None = None,
) -> dict[str, Any]:
    response = admin.post(
        "departments",
        json={
            "name": name,
            "code": code,
            "parent_id": parent_id,
            "manager_user_id": manager_user_id,
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def create_role(admin: ApiClient, *, code: str, name: str) -> dict[str, Any]:
    response = admin.post("roles", json={"code": code, "name": name})
    assert response.status_code in (200, 201), response.text
    return response.json()


def set_role_members(admin: ApiClient, role_id: int, user_ids: list[int]) -> None:
    response = admin.put(f"roles/{role_id}/members", json={"user_ids": user_ids})
    assert response.status_code == 200, response.text


def find_flow(admin: ApiClient, code: str) -> dict[str, Any]:
    response = admin.get("flow-templates?size=200")
    assert response.status_code == 200, response.text
    for flow in response.json():
        if flow.get("code") == code:
            return flow
    raise AssertionError(f"未找到流程模板：{code}")


def create_draft(
    client: ApiClient,
    flow_template_id: int,
    data: dict[str, Any],
    *,
    title: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        "instances/drafts",
        json={"flow_template_id": flow_template_id, "title": title, "data": data},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def update_draft(client: ApiClient, instance_id: int, data: dict[str, Any]) -> dict[str, Any]:
    response = client.put(f"instances/{instance_id}/draft", json={"data": data})
    assert response.status_code == 200, response.text
    return response.json()


def submit(
    client: ApiClient,
    instance_id: int,
    data: dict[str, Any],
    *,
    note: str = "",
    request_id: str | None = None,
) -> Any:
    headers = {"X-Request-Id": request_id} if request_id else None
    return client.post(
        f"instances/{instance_id}/submit",
        json={"data": data, "note": note, "attachment_ids": [], "assignee_picks": {}},
        headers=headers,
    )


def todo(client: ApiClient) -> list[dict[str, Any]]:
    response = client.get("tasks/todo?size=100")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def done(client: ApiClient) -> list[dict[str, Any]]:
    response = client.get("tasks/done?size=100")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def mine(client: ApiClient) -> list[dict[str, Any]]:
    response = client.get("tasks/mine?size=100")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def assignments_for(client: ApiClient, instance_id: int) -> list[dict[str, Any]]:
    return [item for item in todo(client) if item["instance_id"] == instance_id]


def find_assignment(
    client: ApiClient,
    instance_id: int,
    *,
    node_type: str | None = None,
) -> dict[str, Any]:
    items = assignments_for(client, instance_id)
    if node_type:
        items = [item for item in items if item.get("node_type") == node_type]
    assert items, f"未找到实例 {instance_id} 的待办（node_type={node_type}）"
    return items[0]


def act(
    client: ApiClient,
    assignment_id: int,
    *,
    action: str = "AGREE",
    opinion: str = "",
    field_patch: dict[str, Any] | None = None,
    return_target: str | None = None,
    request_id: str | None = None,
) -> Any:
    headers = {"X-Request-Id": request_id} if request_id else None
    body: dict[str, Any] = {
        "action": action,
        "opinion": opinion,
        "attachment_ids": [],
        "field_patch": field_patch or {},
        "return_target": return_target,
    }
    return client.post(f"tasks/assignments/{assignment_id}/act", json=body, headers=headers)


def render(
    client: ApiClient,
    instance_id: int,
    *,
    assignment_id: int | None = None,
) -> Any:
    params = {"assignment_id": assignment_id} if assignment_id else None
    return client.get(f"instances/{instance_id}/render", params=params)


def resubmit(
    client: ApiClient,
    instance_id: int,
    data: dict[str, Any],
    *,
    note: str = "",
    request_id: str | None = None,
) -> Any:
    headers = {"X-Request-Id": request_id} if request_id else None
    return client.post(
        f"instances/{instance_id}/resubmit",
        json={"data": data, "note": note, "attachment_ids": [], "assignee_picks": {}},
        headers=headers,
    )


def withdraw(client: ApiClient, instance_id: int, *, reason: str = "") -> Any:
    return client.post(f"instances/{instance_id}/withdraw", json={"reason": reason})


def terminate(client: ApiClient, instance_id: int, *, reason: str) -> Any:
    return client.post(f"instances/{instance_id}/terminate", json={"reason": reason})


def cc_tasks(client: ApiClient) -> list[dict[str, Any]]:
    response = client.get("tasks/cc?size=100")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def archive(client: ApiClient, params: dict[str, Any] | None = None) -> Any:
    return client.get("instances/archive", params=params or {"size": 100})


def archive_export(client: ApiClient, params: dict[str, Any] | None = None) -> Any:
    return client.get("instances/archive/export", params=params or {})


def export_instance(client: ApiClient, instance_id: int) -> Any:
    return client.get(f"instances/{instance_id}/export")


def transfer(
    client: ApiClient,
    assignment_id: int,
    *,
    to_user_id: int,
    reason: str,
) -> Any:
    return client.post(
        f"tasks/assignments/{assignment_id}/transfer",
        json={"to_user_id": to_user_id, "reason": reason},
    )


def create_delegation(
    client: ApiClient,
    *,
    delegatee_id: int,
    start_at: str,
    end_at: str,
    reason: str,
    flow_template_ids: list[int] | None = None,
) -> Any:
    return client.post(
        "delegations",
        json={
            "delegatee_id": delegatee_id,
            "start_at": start_at,
            "end_at": end_at,
            "reason": reason,
            "flow_template_ids": flow_template_ids or [],
        },
    )


def cancel_delegation(client: ApiClient, delegation_id: int) -> Any:
    return client.post(f"delegations/{delegation_id}/cancel")


def start_reimburse(client: ApiClient, flow_id: int, *, amount: float, reason: str) -> int:
    data = reimburse_data(amount=amount, reason=reason)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def approve_reimburse(
    *,
    zhangsan: ApiClient,
    lisi: ApiClient,
    wangwu: ApiClient,
    admin: ApiClient,
    flow_id: int,
    amount: float = 2500,
    invoice: str = "INV-E2E-001",
    reason: str = "E2E 报销",
) -> int:
    """走完样例报销：部门经理 → 财务双签 → 财务填写 → 通过。"""
    instance_id = start_reimburse(zhangsan, flow_id, amount=amount, reason=reason)
    manager_task = find_assignment(lisi, instance_id)
    assert act(lisi, manager_task["assignment_id"], opinion="同意").status_code == 200

    finance_task = find_assignment(wangwu, instance_id)
    admin_task = find_assignment(admin, instance_id)
    assert act(wangwu, finance_task["assignment_id"], opinion="同意").status_code == 200
    assert act(admin, admin_task["assignment_id"], opinion="同意").status_code == 200

    fill_task = find_assignment(wangwu, instance_id, node_type="FILL")
    filled = act(
        wangwu,
        fill_task["assignment_id"],
        action="SUBMIT",
        opinion="核销完成",
        field_patch={"actualAmount": amount, "invoiceNo": invoice},
    )
    assert filled.status_code == 200, filled.text
    assert filled.json()["status"] == "APPROVED"
    return instance_id


def leave_data(*, reason: str = "E2E 请假") -> dict[str, Any]:
    return {
        "leaveType": "personal",
        "startDate": "2026-11-19",
        "endDate": "2026-11-19",
        "reason": reason,
    }


def reimburse_data(*, amount: float = 2500, reason: str = "E2E 报销") -> dict[str, Any]:
    return {
        "reason": reason,
        "category": "travel",
        "subCategory": "flight",
        "items": [{"name": "机票", "qty": 1, "price": amount}],
    }
