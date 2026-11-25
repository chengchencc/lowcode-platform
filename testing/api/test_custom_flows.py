from __future__ import annotations

import uuid
from typing import Any, Callable

from support.client import ApiClient
from support.factories import (
    act,
    create_dept,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    dept_manager_chain_definition,
    find_assignment,
    parallel_any_definition,
    parallel_return_definition,
    render,
    sequential_definition,
    simple_data,
    submit,
    todo,
)


def _submit(client: ApiClient, flow_id: int, reason: str) -> int:
    data = simple_data(reason=reason)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def test_running_manager_change_affects_only_later_nodes(
    admin_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
    make_user: Callable[..., tuple[ApiClient, dict[str, Any]]],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 组织变更表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 两级主管审批",
        definition=dept_manager_chain_definition(2),
    )

    lisi_id = seed["users"]["lisi"]["id"]
    wangwu_id = seed["users"]["wangwu"]["id"]
    dept = create_dept(
        admin_client,
        name="E2E 组织变更部门",
        code=f"E2E_ORGCHG_{uuid.uuid4().hex[:6].upper()}",
        parent_id=seed["depts"]["HQ"]["id"],
        manager_user_id=lisi_id,
    )
    employee_client, _ = make_user(dept_id=dept["id"], name=f"e2e_orgchg_{uuid.uuid4().hex[:6]}")

    try:
        instance_id = _submit(employee_client, flow["id"], "ORG-02 运行中换主管")

        first = find_assignment(lisi_client, instance_id)
        assert first["user_id"] == lisi_id

        changed = admin_client.put(
            f"departments/{dept['id']}", json={"manager_user_id": wangwu_id}
        )
        assert changed.status_code == 200, changed.text

        # 已派任务不变
        first_after = find_assignment(lisi_client, instance_id)
        assert first_after["user_id"] == lisi_id

        assert act(lisi_client, first_after["assignment_id"], opinion="一审通过").status_code == 200
        second = find_assignment(wangwu_client, instance_id)
        assert second["user_id"] == wangwu_id, "后续节点应按最新组织派给新主管"

        assert act(wangwu_client, second["assignment_id"], opinion="二审通过").status_code == 200
        assert render(employee_client, instance_id).json()["instance"]["status"] == "APPROVED"
    finally:
        employee_client.close()


def test_parallel_any_first_agree_cancels_others(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 或签表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 或签流程",
        definition=parallel_any_definition(
            [seed["users"]["lisi"]["id"], seed["users"]["wangwu"]["id"]]
        ),
    )

    lisi_client = ApiClient.login("lisi", "demo123456")[0]
    wangwu_client = ApiClient.login("wangwu", "demo123456")[0]
    try:
        instance_id = _submit(zhangsan_client, flow["id"], "TASK-03 或签")

        lisi_task = find_assignment(lisi_client, instance_id)
        wangwu_task = find_assignment(wangwu_client, instance_id)
        assert lisi_task["group_id"] == wangwu_task["group_id"]

        approved = act(lisi_client, lisi_task["assignment_id"], opinion="我先同意")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "APPROVED"

        assert [item for item in todo(wangwu_client) if item["instance_id"] == instance_id] == []
        late = act(wangwu_client, wangwu_task["assignment_id"], opinion="已取消")
        assert late.status_code in (400, 403, 404, 409, 422), late.text
    finally:
        lisi_client.close()
        wangwu_client.close()


def test_parallel_member_return_cancels_group_and_redispatches_target(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 并行退回表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 并行退回流程",
        definition=parallel_return_definition(
            target_node_id="a1",
            member_user_ids=[seed["users"]["wangwu"]["id"], seed["users"]["zhaoliu"]["id"]],
        ),
    )

    wangwu_client = ApiClient.login("wangwu", "demo123456")[0]
    zhaoliu_client = ApiClient.login("zhaoliu", "demo123456")[0]
    try:
        instance_id = _submit(zhangsan_client, flow["id"], "D-03 并行组退回")

        # a1 → 并行组
        a1 = find_assignment(wangwu_client, instance_id)
        assert a1["node_name"] == "退回目标审批"
        assert act(wangwu_client, a1["assignment_id"], opinion="一审通过").status_code == 200

        member_task = find_assignment(wangwu_client, instance_id)
        other_task = find_assignment(zhaoliu_client, instance_id)
        assert member_task["group_id"] == other_task["group_id"]

        returned = act(
            wangwu_client,
            member_task["assignment_id"],
            action="RETURN",
            return_target="a1",
            opinion="退回归档",
        )
        assert returned.status_code == 200, returned.text
        assert returned.json()["status"] == "RUNNING"

        # 整组取消 + 目标节点重派
        assert [item for item in todo(zhaoliu_client) if item["instance_id"] == instance_id] == []
        redispatch = find_assignment(wangwu_client, instance_id)
        assert redispatch["node_name"] == "退回目标审批"
        timeline = render(zhangsan_client, instance_id).json()["actions"]
        assert any(action["action"] == "RETURN" for action in timeline)
    finally:
        wangwu_client.close()
        zhaoliu_client.close()


def _revoke_flow(
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> dict[str, Any]:
    form = create_form_and_publish(admin_client, name="E2E 撤回审批表单")
    return create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 撤回审批流程",
        definition=sequential_definition(
            [
                ("a1", "一级审批", seed["users"]["lisi"]["id"]),
                ("a2", "二级审批", seed["users"]["wangwu"]["id"]),
                ("a3", "三级审批", seed["users"]["zhaoliu"]["id"]),
            ]
        ),
    )


def test_approver_can_revoke_own_approval_before_downstream_acts(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    """TASK-08：本人同意、下游未处理时可撤回；下游待办取消并重派本人节点。"""
    flow = _revoke_flow(admin_client, seed)
    instance_id = _submit(zhangsan_client, flow["id"], "TASK-08 撤回审批")

    first = find_assignment(lisi_client, instance_id)
    assert act(lisi_client, first["assignment_id"], opinion="先同意").status_code == 200
    # 下游已派给王五
    assert find_assignment(wangwu_client, instance_id)["node_name"] == "二级审批"

    detail = render(lisi_client, instance_id).json()
    assert detail["revocable_approval"] == {
        "assignment_id": first["assignment_id"],
        "node_name": "一级审批",
    }

    revoked = lisi_client.post(
        f"tasks/assignments/{first['assignment_id']}/revoke",
        json={"reason": "意见要改"},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "RUNNING"

    # 下游待办被取消；一级节点重新派回李四
    assert [row for row in todo(wangwu_client) if row["instance_id"] == instance_id] == []
    reopened = find_assignment(lisi_client, instance_id)
    assert reopened["node_name"] == "一级审批"
    assert reopened["assignment_id"] != first["assignment_id"]

    # 历史动作保留，并出现「撤回审批」
    actions = render(lisi_client, instance_id).json()["actions"]
    assert any(action["action"] == "AGREE" for action in actions)
    assert any(
        action["action"] == "REVOKE_APPROVAL" and action["action_label"] == "撤回审批"
        for action in actions
    )
    # 撤回后本人处于待办中，不应再显示撤回入口
    assert render(lisi_client, instance_id).json()["revocable_approval"] is None


def test_revoke_blocked_when_downstream_has_acted(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    flow = _revoke_flow(admin_client, seed)
    instance_id = _submit(zhangsan_client, flow["id"], "TASK-08 下游已处理")
    # 尚无人处理：发起人详情页应给出撤回入口
    assert render(zhangsan_client, instance_id).json()["can_withdraw"] is True

    first = find_assignment(lisi_client, instance_id)
    assert act(lisi_client, first["assignment_id"], opinion="同意").status_code == 200
    # 已有人处理：撤回按钮不再下发（不是点了才报错）
    assert render(zhangsan_client, instance_id).json()["can_withdraw"] is False
    second = find_assignment(wangwu_client, instance_id)
    assert act(wangwu_client, second["assignment_id"], opinion="二级同意").status_code == 200

    response = lisi_client.post(
        f"tasks/assignments/{first['assignment_id']}/revoke", json={}
    )
    assert response.status_code == 422, response.text
    assert "后续节点已有处理" in response.text
    assert render(lisi_client, instance_id).json()["revocable_approval"] is None
