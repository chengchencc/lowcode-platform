"""P0 补齐：流程发布校验与组织变更。

对应矩阵 FLOW-02 / FLOW-03 / ORG-01 / ORG-02 中仍缺的子项。
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from support.client import ApiClient
from support.factories import (
    _approval_node,
    create_dept,
    create_draft,
    create_flow_and_publish,
    create_flow_draft,
    create_form_and_publish,
    create_role,
    create_user,
    dept_manager_chain_definition,
    publish_definition,
    role_rule,
    sequential_definition,
    set_role_members,
    simple_data,
    simple_form_schema,
    submit,
    todo,
    user_rule,
)


def _instance_tasks(client: ApiClient, instance_id: int) -> list[dict[str, Any]]:
    return [item for item in todo(client) if item["instance_id"] == instance_id]


def _submit(client: ApiClient, flow_id: int, reason: str) -> int:
    data = simple_data(reason=reason)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def _codes(response: Any) -> set[str]:
    detail = response.json().get("detail", {})
    return {
        issue["code"]
        for issue in (detail.get("extra") or {}).get("errors", [])
    }


# --------------------------------------------------------------------------- ORG


def test_role_member_change_affects_only_new_tasks(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    make_user: Callable[..., tuple[ApiClient, dict[str, Any]]],
) -> None:
    role = create_role(
        admin_client,
        code=f"e2e_role_{uuid.uuid4().hex[:8]}",
        name="E2E 动态角色",
    )
    first_client, first = make_user()
    second_client, second = make_user()
    try:
        set_role_members(admin_client, role["id"], [first["id"]])

        form = create_form_and_publish(admin_client, name="E2E 角色变更表单")
        flow = create_flow_and_publish(
            admin_client,
            form_template_id=form["id"],
            name="E2E 角色变更流程",
            definition={
                "steps": [
                    _approval_node("a1", "角色审批", role_rule(role["id"]))
                ]
            },
        )

        old_instance = _submit(zhangsan_client, flow["id"], "角色变更-旧")
        assert len(_instance_tasks(first_client, old_instance)) == 1
        assert _instance_tasks(second_client, old_instance) == []

        set_role_members(admin_client, role["id"], [second["id"]])

        new_instance = _submit(zhangsan_client, flow["id"], "角色变更-新")
        assert len(_instance_tasks(second_client, new_instance)) == 1
        assert _instance_tasks(first_client, new_instance) == []
        # 已派任务保持原处理人，不因角色成员变化而迁移
        assert len(_instance_tasks(first_client, old_instance)) == 1
    finally:
        first_client.close()
        second_client.close()


def test_dept_move_changes_future_dispatch(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
    make_user: Callable[..., tuple[ApiClient, dict[str, Any]]],
) -> None:
    hq = seed["depts"]["HQ"]
    lisi_id = seed["users"]["lisi"]["id"]
    wangwu_id = seed["users"]["wangwu"]["id"]

    left = create_dept(
        admin_client,
        name="E2E 左侧部门",
        code=f"E2E_LEFT_{uuid.uuid4().hex[:6].upper()}",
        parent_id=hq["id"],
        manager_user_id=lisi_id,
    )
    right = create_dept(
        admin_client,
        name="E2E 右侧部门",
        code=f"E2E_RIGHT_{uuid.uuid4().hex[:6].upper()}",
        parent_id=hq["id"],
        manager_user_id=wangwu_id,
    )
    child = create_dept(
        admin_client,
        name="E2E 移动子部门",
        code=f"E2E_MOVE_{uuid.uuid4().hex[:6].upper()}",
        parent_id=left["id"],
    )
    employee_client, _ = make_user(dept_id=child["id"])
    try:
        form = create_form_and_publish(admin_client, name="E2E 部门移动表单")
        flow = create_flow_and_publish(
            admin_client,
            form_template_id=form["id"],
            name="E2E 部门移动流程",
            definition=dept_manager_chain_definition(1),
        )

        before = _submit(employee_client, flow["id"], "部门移动-移动前")
        assert _instance_tasks(lisi_client, before) != []
        assert _instance_tasks(employee_client, before) == []

        moved = admin_client.put(
            f"departments/{child['id']}",
            json={"parent_id": right["id"]},
        )
        assert moved.status_code == 200, moved.text

        after = _submit(employee_client, flow["id"], "部门移动-移动后")
        assert len(_instance_tasks(wangwu_client, after)) == 1
        assert _instance_tasks(lisi_client, after) == []
        # 移动前已派的任务不丢，仍在原主管名下
        assert len(_instance_tasks(lisi_client, before)) == 1
    finally:
        employee_client.close()


# --------------------------------------------------------------------------- FLOW


def test_publish_rejects_condition_field_missing(admin_client: ApiClient, seed: dict[str, Any]) -> None:
    form = create_form_and_publish(admin_client, name="E2E 条件字段缺失表单")
    flow, version_id = create_flow_draft(
        admin_client, form_template_id=form["id"], name="E2E 条件字段缺失流程"
    )
    definition = sequential_definition([("a1", "审批", seed["users"]["lisi"]["id"])])
    definition["steps"].append(
        {
            "id": "c1",
            "name": "引用已删除字段",
            "type": "condition",
            "branches": [
                {
                    "id": "b1",
                    "when": {
                        "op": "and",
                        "conditions": [{"field": "ghost", "cmp": ">", "value": 1}],
                    },
                    "steps": [],
                },
                {"id": "else", "when": None, "steps": []},
            ],
        }
    )
    published = publish_definition(admin_client, version_id, definition)
    assert published.status_code == 422, published.text
    assert "CONDITION_FIELD_MISSING" in _codes(published)
    assert admin_client.get(f"flow-templates/{flow['id']}").json()["status"] != "PUBLISHED"


def test_publish_rejects_permission_field_missing(
    admin_client: ApiClient, seed: dict[str, Any]
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 权限字段缺失表单")
    flow, version_id = create_flow_draft(
        admin_client, form_template_id=form["id"], name="E2E 权限字段缺失流程"
    )
    definition = sequential_definition([("a1", "审批", seed["users"]["lisi"]["id"])])
    definition["steps"][0]["fields_permission"]["overrides"] = {"ghost": "hidden"}
    published = publish_definition(admin_client, version_id, definition)
    assert published.status_code == 422, published.text
    assert "PERMISSION_FIELD_MISSING" in _codes(published)
    assert admin_client.get(f"flow-templates/{flow['id']}").json()["status"] != "PUBLISHED"


def test_deep_nested_conditions_do_not_500(admin_client: ApiClient, seed: dict[str, Any]) -> None:
    form = create_form_and_publish(admin_client, name="E2E 深嵌套表单")
    flow, version_id = create_flow_draft(
        admin_client, form_template_id=form["id"], name="E2E 深嵌套流程"
    )
    inner: dict[str, Any] = _approval_node(
        "a1", "最内层审批", user_rule(seed["users"]["lisi"]["id"])
    )
    for index in range(40):
        inner = {
            "id": f"c{index}",
            "name": f"嵌套条件{index}",
            "type": "condition",
            "branches": [
                {
                    "id": f"b{index}",
                    "when": {
                        "op": "and",
                        "conditions": [{"field": "amount", "cmp": ">", "value": index}],
                    },
                    "steps": [inner],
                },
                {"id": f"else{index}", "when": None, "steps": []},
            ],
        }
    published = publish_definition(admin_client, version_id, {"steps": [inner]})
    assert published.status_code in (200, 422), published.text
    if published.status_code == 422:
        assert admin_client.get(f"flow-templates/{flow['id']}").json()["status"] != "PUBLISHED"


def test_republish_rejects_field_removed_from_form(
    admin_client: ApiClient, seed: dict[str, Any]
) -> None:
    schema = simple_form_schema()
    form = create_form_and_publish(
        admin_client, name="E2E 删字段表单", schema=schema
    )
    flow, version_id = create_flow_draft(
        admin_client, form_template_id=form["id"], name="E2E 删字段流程"
    )
    definition = sequential_definition([("a1", "审批", seed["users"]["lisi"]["id"])])
    definition["steps"].append(
        {
            "id": "c1",
            "name": "按金额分流",
            "type": "condition",
            "branches": [
                {
                    "id": "b1",
                    "when": {
                        "op": "and",
                        "conditions": [{"field": "amount", "cmp": ">", "value": 100}],
                    },
                    "steps": [],
                },
                {"id": "else", "when": None, "steps": []},
            ],
        }
    )
    assert publish_definition(admin_client, version_id, definition).status_code == 200

    versions = admin_client.get(f"form-templates/{form['id']}/versions").json()
    published_version = next(item for item in versions if item["status"] == "PUBLISHED")
    new_draft = admin_client.post(
        f"form-templates/{form['id']}/versions",
        json={"from_version_id": published_version["id"]},
    )
    assert new_draft.status_code in (200, 201), new_draft.text
    draft_id = new_draft.json()["id"]

    reduced = simple_form_schema()
    reduced["sections"][0]["fields"] = [
        field for field in reduced["sections"][0]["fields"] if field["key"] != "amount"
    ]
    saved = admin_client.put(
        f"form-versions/{draft_id}", json={"schema_data": reduced}
    )
    assert saved.status_code == 200, saved.text
    assert admin_client.post(f"form-versions/{draft_id}/publish", json={}).status_code == 200

    flow_draft = admin_client.post(f"flow-templates/{flow['id']}/versions")
    assert flow_draft.status_code in (200, 201), flow_draft.text
    republished = admin_client.post(
        f"flow-versions/{flow_draft.json()['id']}/publish", json={"remark": "E2E 重发"}
    )
    assert republished.status_code == 422, republished.text
    assert "CONDITION_FIELD_MISSING" in _codes(republished)
