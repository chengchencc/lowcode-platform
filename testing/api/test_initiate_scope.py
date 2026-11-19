from __future__ import annotations

import uuid
from typing import Any, Callable

from support.client import ApiClient
from support.factories import (
    create_dept,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    create_role,
    sequential_definition,
    set_role_members,
    simple_data,
)


def _available_flow_ids(client: ApiClient) -> set[int]:
    response = client.get("instances/available-flows")
    assert response.status_code == 200, response.text
    return {flow["id"] for flow in response.json()}


def test_role_scope_limits_start_center_and_direct_access(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    make_user: Callable[..., tuple[ApiClient, dict[str, Any]]],
    seed: dict[str, Any],
) -> None:
    role = create_role(
        admin_client,
        code=f"e2e_scope_{uuid.uuid4().hex[:6]}",
        name="E2E 发起范围角色",
    )
    member_client, member = make_user(role_ids=[role["id"]])
    set_role_members(admin_client, role["id"], [member["id"]])

    form = create_form_and_publish(admin_client, name="E2E 角色范围表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 角色范围流程",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
        initiator_scope={"type": "role", "role_ids": [role["id"]]},
    )

    assert flow["id"] in _available_flow_ids(member_client)
    assert flow["id"] not in _available_flow_ids(zhangsan_client)
    assert member_client.get(f"instances/start-options/{flow['id']}").status_code == 200
    assert zhangsan_client.get(f"instances/start-options/{flow['id']}").status_code in (403, 404)

    blocked = zhangsan_client.post(
        "instances/drafts",
        json={"flow_template_id": flow["id"], "data": simple_data(reason="越权发起")},
    )
    assert blocked.status_code in (403, 404), blocked.text

    allowed = create_draft(member_client, flow["id"], simple_data(reason="角色范围内发起"))
    assert allowed["id"]


def test_dept_scope_includes_child_departments(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    make_user: Callable[..., tuple[ApiClient, dict[str, Any]]],
    seed: dict[str, Any],
) -> None:
    parent = create_dept(
        admin_client,
        name="E2E 范围母部门",
        code=f"E2E_SCOPE_P_{uuid.uuid4().hex[:6].upper()}",
        parent_id=seed["depts"]["HQ"]["id"],
    )
    child = create_dept(
        admin_client,
        name="E2E 范围子部门",
        code=f"E2E_SCOPE_C_{uuid.uuid4().hex[:6].upper()}",
        parent_id=parent["id"],
    )
    employee_client, _ = make_user(dept_id=child["id"])

    form = create_form_and_publish(admin_client, name="E2E 部门范围表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 部门范围流程",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
        initiator_scope={"type": "dept", "dept_ids": [parent["id"]]},
    )

    assert flow["id"] in _available_flow_ids(employee_client)
    assert flow["id"] not in _available_flow_ids(zhangsan_client)
    assert employee_client.get(f"instances/start-options/{flow['id']}").status_code == 200
    employee_client.close()
