"""P0 补齐：自动填充/标题/只读、双会话提交、审批人来源、编号语义。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from support.client import ApiClient
from support.factories import (
    _approval_node,
    create_dept,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    find_assignment,
    prev_node_rule,
    render,
    sequential_definition,
    simple_form_schema,
    submit,
    todo,
    user_rule,
)


def _user_ids(admin: ApiClient) -> dict[str, int]:
    items = admin.get("users?size=100").json()["items"]
    return {item["username"]: item["id"] for item in items}


def test_auto_fill_title_and_readonly_fields(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    schema = {
        "model_version": 1,
        "title_field": "titleText",
        "sections": [
            {
                "key": "sec",
                "title": "申请",
                "stage": "apply",
                "fields": [
                    {"key": "titleText", "label": "标题", "type": "text", "required": True},
                    {
                        "key": "applicant",
                        "label": "发起人",
                        "type": "user",
                        "auto_fill": "initiator",
                    },
                    {
                        "key": "applyDept",
                        "label": "发起部门",
                        "type": "dept",
                        "auto_fill": "initiator_dept",
                    },
                    {
                        "key": "total",
                        "label": "合计",
                        "type": "formula",
                        "formula": {"type": "arithmetic", "expression": "1 + 1"},
                    },
                    {
                        "key": "secret",
                        "label": "补充",
                        "type": "text",
                        "visible_at_start": False,
                    },
                ],
            }
        ],
    }
    form = create_form_and_publish(
        admin_client, name="E2E 自动填充表单", schema=schema
    )
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 自动填充流程",
        definition=sequential_definition([("a1", "审批", _user_ids(admin_client)["lisi"])]),
    )

    options = zhangsan_client.get(f"instances/start-options/{flow['id']}")
    assert options.status_code == 200, options.text
    body = options.json()
    assert body["auto_fill_values"]["applicant"] == seed["users"]["zhangsan"]["id"]
    assert body["auto_fill_values"]["applyDept"] == seed["users"]["zhangsan"]["dept_id"]
    assert body["permissions"]["total"]["editable"] is False
    assert "secret" not in body["permissions"]

    data = {"titleText": "自动填充标题"}
    draft = create_draft(zhangsan_client, flow["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text
    instance = submitted.json()
    assert instance["title"] == "自动填充标题"

    rendered = render(zhangsan_client, draft["id"]).json()
    assert rendered["values"]["applicant"] == seed["users"]["zhangsan"]["id"]
    assert rendered["values"]["applyDept"] == seed["users"]["zhangsan"]["dept_id"]


def test_dual_session_submit_creates_one_task(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    db_dialect: str,
) -> None:
    if db_dialect == "sqlite":
        import pytest

        pytest.skip("SQLite 无行锁，双会话提交并发需在 MySQL 环境验证")
    form = create_form_and_publish(admin_client, name="E2E 双会话提交表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 双会话提交流程",
        definition=sequential_definition([("a1", "审批", _user_ids(admin_client)["lisi"])]),
    )
    data = {"reason": "双会话提交", "amount": 100}
    draft = create_draft(zhangsan_client, flow["id"], data)
    instance_id = draft["id"]

    second, _ = ApiClient.login("zhangsan", "demo123456")
    try:
        def fire(client: ApiClient, request_id: str) -> int:
            return submit(
                client,
                instance_id,
                data,
                request_id=request_id,
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(
                pool.map(
                    lambda args: fire(*args),
                    [(zhangsan_client, "dual-a"), (second, "dual-b")],
                )
            )
    finally:
        second.close()

    assert all(status in (200, 409, 422) for status in statuses), statuses
    assert any(status == 200 for status in statuses), statuses

    tasks = [item for item in todo(lisi_client) if item["instance_id"] == instance_id]
    assert len(tasks) == 1, "并发提交不得产生多条任务"
    timeline = zhangsan_client.get(f"instances/{instance_id}/timeline").json()
    assert len([row for row in timeline if row["action"] == "SUBMIT"]) == 1


def test_prev_node_and_fixed_dept_approver_sources(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    ids = _user_ids(admin_client)
    fixed_dept = create_dept(
        admin_client,
        name="E2E 指定部门",
        code="E2E_FIXED_DEPT",
        parent_id=seed["depts"]["HQ"]["id"],
        manager_user_id=ids["lisi"],
    )
    form = create_form_and_publish(admin_client, name="E2E 指定来源表单")

    first = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 上一节点来源",
        definition={
            "steps": [
                _approval_node("a1", "初审", user_rule(ids["lisi"])),
                _approval_node("a2", "复核", prev_node_rule()),
            ]
        },
    )
    data = {"reason": "上一节点来源", "amount": 100}
    draft = create_draft(zhangsan_client, first["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200
    first_task = find_assignment(lisi_client, draft["id"])
    acted = lisi_client.post(
        f"tasks/assignments/{first_task['assignment_id']}/act",
        json={"action": "AGREE", "opinion": "初审", "attachment_ids": [], "field_patch": {}},
    )
    assert acted.status_code == 200, acted.text
    second_tasks = [item for item in todo(lisi_client) if item["instance_id"] == draft["id"]]
    assert len(second_tasks) == 1
    assert second_tasks[0]["node_name"] == "复核"

    fixed = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 指定部门来源",
        definition={
            "steps": [
                {
                    "id": "a1",
                    "name": "指定部门主管",
                    "type": "approval",
                    "assignee": {
                        "mode": "SINGLE",
                        "sources": [
                            {"type": "dept_manager", "dept_ids": [fixed_dept["id"]]}
                        ],
                    },
                }
            ]
        },
    )
    data2 = {"reason": "指定部门来源", "amount": 100}
    draft2 = create_draft(zhangsan_client, fixed["id"], data2)
    assert submit(zhangsan_client, draft2["id"], data2).status_code == 200
    assert len([item for item in todo(lisi_client) if item["instance_id"] == draft2["id"]]) == 1


def test_auto_number_is_separate_from_instance_code(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
) -> None:
    schema = simple_form_schema()
    schema["sections"][0]["fields"].append(
        {
            "key": "docNo",
            "label": "表单编号",
            "type": "text",
            "sort": 9,
            "auto_number": {"prefix": "REQ", "seq_length": 4},
        }
    )
    form = create_form_and_publish(
        admin_client, name="E2E 编号语义表单", schema=schema
    )
    configured = admin_client.put(
        f"form-templates/{form['id']}/search-fields",
        json={"field_keys": ["docNo", "reason"]},
    )
    assert configured.status_code == 200, configured.text

    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 编号语义流程",
        definition=sequential_definition([("a1", "审批", _user_ids(admin_client)["lisi"])]),
    )
    data = {"reason": "编号语义", "amount": 100}
    draft = create_draft(zhangsan_client, flow["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200

    rendered = render(zhangsan_client, draft["id"]).json()
    doc_no = rendered["values"]["docNo"]
    instance_code = rendered["instance"]["code"]
    assert doc_no.startswith("REQ")
    assert instance_code != doc_no
    assert instance_code.startswith("LX") or instance_code[0].isalpha()

    by_form_no = admin_client.get(
        "instances",
        params={
            "scope": "all",
            "flow_template_id": flow["id"],
            "size": 100,
            "filters": json.dumps(
                [{"field": "docNo", "op": "contains", "value": doc_no}]
            ),
        },
    )
    assert by_form_no.status_code == 200, by_form_no.text
    assert [item["id"] for item in by_form_no.json()["items"]] == [draft["id"]]

    by_instance_code = admin_client.get(
        "instances",
        params={"scope": "all", "size": 100, "keyword": instance_code},
    )
    assert by_instance_code.status_code == 200, by_instance_code.text
    assert draft["id"] in [item["id"] for item in by_instance_code.json()["items"]]
