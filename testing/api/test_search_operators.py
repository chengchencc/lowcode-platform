from __future__ import annotations

import json
from typing import Any

from support.client import ApiClient
from support.factories import (
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    search_data,
    search_form_schema,
    sequential_definition,
    submit,
)


def _configure(admin: ApiClient, form_id: int) -> None:
    response = admin.put(
        f"form-templates/{form_id}/search-fields",
        json={
            "field_keys": [
                "reason",
                "leaveDate",
                "urgent",
                "category",
                "tags",
                "owner",
                "dept",
            ]
        },
    )
    assert response.status_code == 200, response.text


def _create(client: ApiClient, flow_id: int, data: dict[str, Any]) -> int:
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def test_date_bool_option_multi_user_dept_filters(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(
        admin_client, name="E2E 检索操作符表单", schema=search_form_schema()
    )
    _configure(admin_client, form["id"])
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 检索操作符流程",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
    )

    lisi = seed["users"]["lisi"]["id"]
    wangwu = seed["users"]["wangwu"]["id"]
    tech = seed["depts"]["TECH"]["id"]
    finance = seed["depts"]["FINANCE"]["id"]

    a = _create(
        zhangsan_client,
        flow["id"],
        search_data(
            reason="alpha",
            amount=100,
            leave_date="2026-11-10",
            urgent=True,
            category="travel",
            tags=["urgent", "normal"],
            owner=lisi,
            dept=tech,
        ),
    )
    b = _create(
        zhangsan_client,
        flow["id"],
        search_data(
            reason="beta",
            amount=500,
            leave_date="2026-12-01",
            urgent=False,
            category="office",
            tags=["normal"],
            owner=wangwu,
            dept=finance,
        ),
    )
    c = _create(
        zhangsan_client,
        flow["id"],
        search_data(
            reason="gamma",
            amount=1000,
            leave_date="2026-10-31",
            urgent=True,
            category="travel",
            tags=[],
            owner=lisi,
            dept=tech,
        ),
    )

    def ids(filters: list[dict[str, Any]]) -> set[int]:
        response = admin_client.get(
            "instances",
            params={
                "scope": "all",
                "flow_template_id": flow["id"],
                "size": 100,
                "filters": json.dumps(filters, ensure_ascii=False),
            },
        )
        assert response.status_code == 200, response.text
        return {item["id"] for item in response.json()["items"]}

    assert ids([{"field": "leaveDate", "op": "between", "value": ["2026-11-01", "2026-11-30"]}]) == {a}
    assert ids([{"field": "leaveDate", "op": "gte", "value": "2026-11-01"}]) == {a, b}
    assert ids([{"field": "urgent", "op": "eq", "value": True}]) == {a, c}
    assert ids([{"field": "category", "op": "in", "value": ["travel"]}]) == {a, c}
    assert ids([{"field": "tags", "op": "has_any", "value": ["urgent"]}]) == {a}
    assert ids([{"field": "tags", "op": "has_all", "value": ["urgent", "normal"]}]) == {a}
    assert ids([{"field": "owner", "op": "eq", "value": lisi}]) == {a, c}
    assert ids([{"field": "dept", "op": "eq", "value": tech}]) == {a, c}
    assert ids([{"field": "reason", "op": "is_empty"}]) == set()
    assert ids([{"field": "reason", "op": "is_not_empty"}]) == {a, b, c}
