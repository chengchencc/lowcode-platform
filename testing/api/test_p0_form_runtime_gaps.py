"""P0 补齐：旧实例版本、服务端值规则、并发处理、首页空状态。"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from support.client import ApiClient
from support.factories import (
    act,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    find_assignment,
    parallel_any_definition,
    render,
    sequential_definition,
    simple_form_schema,
    submit,
)


def _schema_keys(body: dict[str, Any]) -> set[str]:
    return {
        field["key"]
        for section in (body.get("schema_data") or {}).get("sections", [])
        for field in section.get("fields", [])
    }


def _publish_new_form_version(
    admin: ApiClient, form_id: int, schema: dict[str, Any]
) -> dict[str, Any]:
    versions = admin.get(f"form-templates/{form_id}/versions").json()
    published = next(item for item in versions if item["status"] == "PUBLISHED")
    draft = admin.post(
        f"form-templates/{form_id}/versions",
        json={"from_version_id": published["id"]},
    )
    assert draft.status_code in (200, 201), draft.text
    draft_id = draft.json()["id"]
    saved = admin.put(f"form-versions/{draft_id}", json={"schema_data": schema})
    assert saved.status_code == 200, saved.text
    published_new = admin.post(f"form-versions/{draft_id}/publish", json={})
    assert published_new.status_code == 200, published_new.text
    return published_new.json()


def test_old_instance_keeps_old_form_schema(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 旧实例版本表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 旧实例版本流程",
        definition=sequential_definition([("a1", "审批", seed["users"]["lisi"]["id"])]),
    )
    data = {"reason": "旧实例", "amount": 100}
    draft = create_draft(zhangsan_client, flow["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200

    original = render(zhangsan_client, draft["id"]).json()
    assert "note" not in _schema_keys(original)

    new_schema = simple_form_schema()
    new_schema["sections"][0]["fields"].append(
        {"key": "note", "label": "备注", "type": "text", "sort": 9}
    )
    _publish_new_form_version(admin_client, form["id"], new_schema)

    again = render(zhangsan_client, draft["id"]).json()
    assert "note" not in _schema_keys(again)
    assert again["instance"]["form_version_id"] == original["instance"]["form_version_id"]

    # 审批人视角同样按旧版渲染
    assignment = find_assignment(lisi_client, draft["id"])
    handler = render(
        lisi_client, draft["id"], assignment_id=assignment["assignment_id"]
    ).json()
    assert "note" not in _schema_keys(handler)


def test_server_side_value_rules_reject_bypass(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    schema = {
        "model_version": 1,
        "title_field": "reason",
        "sections": [
            {
                "key": "sec",
                "title": "申请",
                "stage": "apply",
                "fields": [
                    {"key": "reason", "label": "事由", "type": "text", "required": True,
                     "validators": {"max_length": 5}},
                    {"key": "amount", "label": "金额", "type": "number",
                     "validators": {"min": 10, "max": 100}},
                    {
                        "key": "items",
                        "label": "明细",
                        "type": "subtable",
                        "validators": {"min_rows": 1, "max_rows": 3},
                        "columns": [
                            {"key": "name", "label": "项目", "type": "text", "required": True}
                        ],
                    },
                ],
            }
        ],
    }
    form = create_form_and_publish(
        admin_client, name="E2E 值规则表单", schema=schema
    )
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 值规则流程",
        definition=sequential_definition([("a1", "审批", seed["users"]["lisi"]["id"])]),
    )
    draft = create_draft(zhangsan_client, flow["id"], {})

    base = {"reason": "正常", "amount": 50, "items": [{"name": "项目A"}]}
    too_small = submit(zhangsan_client, draft["id"], {**base, "amount": 5})
    assert too_small.status_code == 422, too_small.text

    too_long = submit(zhangsan_client, draft["id"], {**base, "reason": "超过五个字符"})
    assert too_long.status_code == 422, too_long.text

    empty_rows = submit(zhangsan_client, draft["id"], {**base, "items": []})
    assert empty_rows.status_code == 422, empty_rows.text

    valid = submit(zhangsan_client, draft["id"], base)
    assert valid.status_code == 200, valid.text


def test_dual_act_same_assignment_mysql_only(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    db_dialect: str,
) -> None:
    if db_dialect == "sqlite":
        import pytest

        pytest.skip("SQLite 无行锁，同一任务并发处理需在 MySQL 环境验证")

    users = admin_client.get("users?size=100").json()["items"]
    lisi_id = next(user["id"] for user in users if user["username"] == "lisi")
    form = create_form_and_publish(admin_client, name="E2E 并发处理表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 并发处理流程",
        definition=sequential_definition([("a1", "审批", lisi_id)]),
    )
    data = {"reason": "并发处理", "amount": 100}
    draft = create_draft(zhangsan_client, flow["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200
    instance_id = draft["id"]

    first, _ = ApiClient.login("lisi", "demo123456")
    second, _ = ApiClient.login("lisi", "demo123456")
    try:
        assignment = find_assignment(first, instance_id)
        barrier = threading.Barrier(2)

        def fire(client: ApiClient) -> int:
            barrier.wait(timeout=5)
            return act(client, assignment["assignment_id"], opinion="并发同意").status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = [
                future.result(timeout=20)
                for future in [pool.submit(fire, first), pool.submit(fire, second)]
            ]
    finally:
        first.close()
        second.close()

    assert 500 not in statuses, statuses
    assert 200 in statuses, statuses
    timeline = zhangsan_client.get(f"instances/{instance_id}/timeline").json()
    assert len([row for row in timeline if row["action"] == "AGREE"]) == 1


def test_act_on_cancelled_any_sign_assignment_is_rejected(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 取消任务表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 取消任务流程",
        definition=parallel_any_definition(
            [seed["users"]["lisi"]["id"], seed["users"]["wangwu"]["id"]]
        ),
    )
    data = {"reason": "取消任务", "amount": 100}
    draft = create_draft(zhangsan_client, flow["id"], data)
    assert submit(zhangsan_client, draft["id"], data).status_code == 200

    lisi, _ = ApiClient.login("lisi", "demo123456")
    wangwu, _ = ApiClient.login("wangwu", "demo123456")
    try:
        lisi_task = find_assignment(lisi, draft["id"])
        wangwu_task = find_assignment(wangwu, draft["id"])
        assert act(lisi, lisi_task["assignment_id"], opinion="先同意").status_code == 200

        cancelled = act(
            wangwu, wangwu_task["assignment_id"], opinion="已取消后再处理"
        )
        assert cancelled.status_code in (409, 422), cancelled.text
        remaining = [
            item
            for item in wangwu.get("tasks/todo?size=100").json()["items"]
            if item["instance_id"] == draft["id"]
        ]
        assert remaining == []
    finally:
        lisi.close()
        wangwu.close()


def test_dashboard_empty_state(
    zhangsan_client: ApiClient,
    make_user: Callable[..., tuple[ApiClient, dict[str, Any]]],
) -> None:
    client, _ = make_user()
    try:
        response = client.get("dashboard/overview")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["admin"] is None
        assert body["personal"]["todo"] == 0
        assert body["personal"]["mine_running"] == 0
        assert body["personal"]["cc_unread"] == 0
    finally:
        client.close()
