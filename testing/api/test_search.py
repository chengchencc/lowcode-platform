from __future__ import annotations

import json
from typing import Any

from support.client import ApiClient
from support.factories import (
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    sequential_definition,
    simple_data,
    submit,
)


def _configure_search_fields(admin: ApiClient, form_id: int, keys: list[str]) -> Any:
    return admin.put(
        f"form-templates/{form_id}/search-fields", json={"field_keys": keys}
    )


def _create_instance(
    client: ApiClient, flow_id: int, *, reason: str, amount: float
) -> int:
    data = simple_data(reason=reason, amount=amount)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def test_business_field_filters(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 检索表单")
    configured = _configure_search_fields(admin_client, form["id"], ["reason", "amount"])
    assert configured.status_code == 200, configured.text

    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 检索流程",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
    )

    alpha = _create_instance(zhangsan_client, flow["id"], reason="alpha 项目", amount=100)
    beta = _create_instance(zhangsan_client, flow["id"], reason="beta 项目", amount=500)
    alpha2 = _create_instance(zhangsan_client, flow["id"], reason="alpha 二号", amount=5000)

    def query(client: ApiClient, *, scope: str, filters: Any) -> Any:
        return client.get(
            "instances",
            params={
                "scope": scope,
                "flow_template_id": flow["id"],
                "size": 100,
                "filters": json.dumps(filters, ensure_ascii=False),
            },
        )

    contains = query(
        admin_client,
        scope="all",
        filters=[{"field": "reason", "op": "contains", "value": "alpha"}],
    )
    assert contains.status_code == 200, contains.text
    ids = {item["id"] for item in contains.json()["items"]}
    assert {alpha, alpha2} <= ids and beta not in ids

    equals = query(
        admin_client,
        scope="all",
        filters=[{"field": "reason", "op": "eq", "value": "beta 项目"}],
    )
    assert equals.status_code == 200, equals.text
    assert [item["id"] for item in equals.json()["items"]] == [beta]

    between = query(
        admin_client,
        scope="all",
        filters=[{"field": "amount", "op": "between", "value": [200, 6000]}],
    )
    assert between.status_code == 200, between.text
    range_ids = {item["id"] for item in between.json()["items"]}
    assert {beta, alpha2} <= range_ids and alpha not in range_ids

    combined = query(
        admin_client,
        scope="all",
        filters=[
            {"field": "reason", "op": "contains", "value": "alpha"},
            {"field": "amount", "op": "gte", "value": 5000},
        ],
    )
    assert combined.status_code == 200, combined.text
    assert [item["id"] for item in combined.json()["items"]] == [alpha2]

    # 普通用户「我发起的」也能按发起阶段可见字段筛选
    mine = query(
        zhangsan_client,
        scope="mine",
        filters=[{"field": "reason", "op": "contains", "value": "alpha"}],
    )
    assert mine.status_code == 200, mine.text
    mine_ids = {item["id"] for item in mine.json()["items"]}
    assert {alpha, alpha2} <= mine_ids and beta not in mine_ids


def test_search_filter_errors_and_scope(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 检索错误表单")
    _configure_search_fields(admin_client, form["id"], ["reason"])
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 检索错误流程",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
    )
    _create_instance(zhangsan_client, flow["id"], reason="alpha", amount=1)

    missing_flow = admin_client.get(
        "instances",
        params={
            "scope": "all",
            "filters": json.dumps([{"field": "reason", "op": "eq", "value": "alpha"}]),
        },
    )
    assert missing_flow.status_code == 422, missing_flow.text
    assert missing_flow.json()["detail"]["code"] == "FLOW_TEMPLATE_REQUIRED"

    unknown_field = admin_client.get(
        "instances",
        params={
            "scope": "all",
            "flow_template_id": flow["id"],
            "filters": json.dumps([{"field": "no_such", "op": "eq", "value": "x"}]),
        },
    )
    assert unknown_field.status_code == 422, unknown_field.text

    bad_scope = zhangsan_client.get(
        "instances",
        params={
            "scope": "all",
            "flow_template_id": flow["id"],
            "filters": json.dumps([{"field": "reason", "op": "eq", "value": "alpha"}]),
        },
    )
    assert bad_scope.status_code in (400, 403, 422), bad_scope.text


def test_rebuild_and_remove_search_fields(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 检索重建表单")
    _configure_search_fields(admin_client, form["id"], ["reason", "amount"])
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 检索重建流程",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
    )
    instance_id = _create_instance(zhangsan_client, flow["id"], reason="rebuild", amount=10)

    rebuilt = admin_client.post(f"form-templates/{form['id']}/search-fields/rebuild")
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()["processed"] >= 1

    still = admin_client.get(
        "instances",
        params={
            "scope": "all",
            "flow_template_id": flow["id"],
            "filters": json.dumps([{"field": "reason", "op": "eq", "value": "rebuild"}]),
        },
    )
    assert still.status_code == 200, still.text
    assert instance_id in {item["id"] for item in still.json()["items"]}

    removed = _configure_search_fields(admin_client, form["id"], [])
    assert removed.status_code == 200, removed.text
    invalid = admin_client.get(
        "instances",
        params={
            "scope": "all",
            "flow_template_id": flow["id"],
            "filters": json.dumps([{"field": "reason", "op": "eq", "value": "rebuild"}]),
        },
    )
    assert invalid.status_code == 422, invalid.text


def test_search_field_metadata(zhangsan_client: ApiClient, admin_client: ApiClient, seed: dict[str, Any]) -> None:
    form = create_form_and_publish(admin_client, name="E2E 检索元数据表单")
    _configure_search_fields(admin_client, form["id"], ["reason", "amount"])
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 检索元数据流程",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
    )
    response = zhangsan_client.get(
        "instances/search-fields",
        params={"flow_template_id": flow["id"], "scope": "mine"},
    )
    assert response.status_code == 200, response.text
    fields = {item["field_key"]: item for item in response.json()}
    assert fields["reason"]["filter_kind"] == "text"
    assert fields["amount"]["filter_kind"] == "number"
