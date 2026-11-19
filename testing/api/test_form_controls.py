from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    full_data,
    full_form_schema,
    render,
    sequential_definition,
    submit,
)


def test_full_control_form_publish_and_submit(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(
        admin_client, name="E2E 全控件表单", schema=full_form_schema()
    )
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 全控件流程",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
    )

    options = zhangsan_client.get(f"instances/start-options/{flow['id']}")
    assert options.status_code == 200, options.text
    body = options.json()
    keys = {
        field["key"]
        for section in body["schema_data"]["sections"]
        for field in section["fields"]
    }
    expected = {
        "title_text", "long_text", "qty", "double", "radio_pick", "checks",
        "category", "sub_category", "day", "clock", "moment", "urgent",
        "owner", "reviewers", "dept", "depts", "files", "pictures", "items",
        "intro", "head", "para", "line", "banner",
    }
    assert expected <= keys
    assert body["schema_data"]["layout"]["columns"] == 3
    section = body["schema_data"]["sections"][0]
    assert section["columns"] == 2 and section["collapsible"] is True
    assert body["permissions"]["double"]["editable"] is False

    data = full_data(
        owner=seed["users"]["lisi"]["id"],
        reviewer=seed["users"]["wangwu"]["id"],
        dept=seed["depts"]["TECH"]["id"],
        other_dept=seed["depts"]["FINANCE"]["id"],
    )
    # 展示控件伪造值应被忽略
    data.update({"intro": "hack", "head": "hack", "banner": "hack"})
    draft = create_draft(zhangsan_client, flow["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text

    values = render(zhangsan_client, draft["id"]).json()["values"]
    assert values["title_text"] == "全控件表单"
    assert values["qty"] == 10
    assert values["double"] == 20
    assert values["checks"] == ["x", "y"]
    assert values["owner"] == seed["users"]["lisi"]["id"]
    assert values["reviewers"] == [seed["users"]["lisi"]["id"], seed["users"]["wangwu"]["id"]]
    assert values["dept"] == seed["depts"]["TECH"]["id"]
    assert values["depts"] == [seed["depts"]["TECH"]["id"], seed["depts"]["FINANCE"]["id"]]
    assert values["items"] == [{"name": "项目一", "amount": 3}]
    assert "intro" not in values
    assert "head" not in values
    assert "banner" not in values
