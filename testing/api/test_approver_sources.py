from __future__ import annotations

import uuid
from typing import Any

from support.client import ApiClient
from support.factories import (
    create_dept,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    create_role,
    find_assignment,
    sequential_definition,
    set_role_members,
    simple_form_schema,
    submit,
    todo,
)


def _schema() -> dict[str, Any]:
    schema = simple_form_schema()
    schema["sections"][0]["fields"].extend(
        [
            {"key": "owner", "label": "负责人", "type": "user", "sort": 3,
             "visible_at_start": True},
            {"key": "dept", "label": "部门", "type": "dept", "sort": 4,
             "visible_at_start": True},
        ]
    )
    return schema


def _flow_with_source(
    admin: ApiClient,
    form_id: int,
    seed: dict[str, Any],
    source: dict[str, Any],
    *,
    name: str,
    initiator_select_scope: dict[str, Any] | None = None,
    prevent_self_approval: bool | None = None,
) -> dict[str, Any]:
    definition = sequential_definition(
        [("a1", "审批", seed["users"]["lisi"]["id"])]
    )
    definition["steps"][0]["assignee"] = {
        "mode": "SINGLE",
        "sources": [source],
        "on_empty": "to_admin",
        "initiator_select": initiator_select_scope,
    }
    if prevent_self_approval is not None:
        definition["prevent_self_approval"] = prevent_self_approval
    return create_flow_and_publish(
        admin,
        form_template_id=form_id,
        name=name,
        definition=definition,
    )


def test_form_user_and_dept_field_sources(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(
        admin_client, name="E2E 审批人来源表单", schema=_schema()
    )

    user_flow = _flow_with_source(
        admin_client,
        form["id"],
        seed,
        {"type": "form_user_field", "field": "owner"},
        name="E2E 表单人员来源",
    )
    data = {"reason": "表单人员", "owner": seed["users"]["lisi"]["id"]}
    draft = create_draft(zhangsan_client, user_flow["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200
    assert find_assignment(lisi_client, draft["id"])["user_id"] == seed["users"]["lisi"]["id"]

    dept = create_dept(
        admin_client,
        name="E2E 来源部门",
        code=f"E2E_SRC_{uuid.uuid4().hex[:6].upper()}",
        parent_id=seed["depts"]["HQ"]["id"],
        manager_user_id=seed["users"]["wangwu"]["id"],
    )
    dept_flow = _flow_with_source(
        admin_client,
        form["id"],
        seed,
        {"type": "form_dept_field", "field": "dept"},
        name="E2E 表单部门来源",
    )
    dept_data = {"reason": "表单部门", "dept": dept["id"]}
    dept_draft = create_draft(zhangsan_client, dept_flow["id"], dept_data)
    assert submit(zhangsan_client, dept_draft["id"], dept_data).status_code == 200
    assert (
        find_assignment(wangwu_client, dept_draft["id"])["user_id"]
        == seed["users"]["wangwu"]["id"]
    )


def test_initiator_select_source(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(
        admin_client, name="E2E 发起人指定表单", schema=_schema()
    )
    role = create_role(
        admin_client,
        code=f"e2e_pick_{uuid.uuid4().hex[:6]}",
        name="E2E 候补审批人",
    )
    set_role_members(admin_client, role["id"], [seed["users"]["wangwu"]["id"]])
    flow = _flow_with_source(
        admin_client,
        form["id"],
        seed,
        {"type": "initiator_select"},
        name="E2E 发起人指定流程",
        initiator_select_scope={"type": "role", "role_ids": [role["id"]]},
    )
    options = zhangsan_client.get(f"instances/start-options/{flow['id']}").json()
    assert any(node["node_id"] == "a1" for node in options["initiator_select_nodes"])

    data = {"reason": "发起人指定"}
    draft = create_draft(zhangsan_client, flow["id"], data)
    submitted = submit(
        zhangsan_client,
        draft["id"],
        data,
        assignee_picks={"a1": [seed["users"]["wangwu"]["id"]]},
    )
    assert submitted.status_code == 200, submitted.text
    assert (
        find_assignment(wangwu_client, draft["id"])["user_id"]
        == seed["users"]["wangwu"]["id"]
    )


def test_role_source_excludes_initiator(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    role = create_role(
        admin_client,
        code=f"e2e_self_{uuid.uuid4().hex[:6]}",
        name="E2E 自审角色",
    )
    set_role_members(admin_client, role["id"], [seed["users"]["zhangsan"]["id"]])
    form = create_form_and_publish(
        admin_client, name="E2E 自审表单", schema=_schema()
    )
    flow = _flow_with_source(
        admin_client,
        form["id"],
        seed,
        {"type": "role", "role_ids": [role["id"]]},
        name="E2E 自审排除流程",
    )
    data = {"reason": "发起人自审"}
    draft = create_draft(zhangsan_client, flow["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text

    # 宽口径来源剔除发起人后为空 → 转管理员兜底，发起人不应拿到任务
    assert [item for item in todo(zhangsan_client) if item["instance_id"] == draft["id"]] == []
    assert find_assignment(admin_client, draft["id"])["user_id"] == seed["users"]["admin"]["id"]


def test_role_source_allows_initiator_when_prevent_self_approval_off(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    """流程关闭防自审后，角色里只有发起人时也应派给发起人。"""
    role = create_role(
        admin_client,
        code=f"e2e_self_off_{uuid.uuid4().hex[:6]}",
        name="E2E 允许自审角色",
    )
    set_role_members(admin_client, role["id"], [seed["users"]["zhangsan"]["id"]])
    form = create_form_and_publish(
        admin_client, name="E2E 允许自审表单", schema=_schema()
    )
    flow = _flow_with_source(
        admin_client,
        form["id"],
        seed,
        {"type": "role", "role_ids": [role["id"]]},
        name="E2E 允许自审流程",
        prevent_self_approval=False,
    )
    data = {"reason": "发起人自审"}
    draft = create_draft(zhangsan_client, flow["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text

    task = find_assignment(zhangsan_client, draft["id"])
    assert task["user_id"] == seed["users"]["zhangsan"]["id"]
    assert task["node_name"] == "审批"
