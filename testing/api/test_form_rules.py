from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    render,
    sequential_definition,
    submit,
)


def _schema() -> dict[str, Any]:
    return {
        "model_version": 1,
        "layout": {"label_position": "top", "columns": 1},
        "title_field": "reason",
        "sections": [
            {
                "key": "sec_apply",
                "title": "申请",
                "stage": "apply",
                "fields": [
                    {"key": "reason", "label": "事由", "type": "text", "required": True,
                     "visible_at_start": True},
                    {"key": "amount", "label": "金额", "type": "number",
                     "visible_at_start": True},
                    {"key": "extra", "label": "补充", "type": "text",
                     "visible_at_start": True},
                ],
            }
        ],
        "rules": [
            {
                "id": "hide_extra",
                "name": "金额大于 100 隐藏补充",
                "when": {"op": "and", "conditions": [
                    {"field": "amount", "cmp": ">", "value": 100}
                ]},
                "effects": [{"target": "extra", "effect": "hidden"}],
                "clear_when_hidden": True,
            }
        ],
    }


def test_form_rule_hides_and_clears_field(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(
        admin_client, name="E2E 联动规则表单", schema=_schema()
    )
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 联动规则流程",
        definition=sequential_definition(
            [("a1", "审批", seed["users"]["lisi"]["id"])]
        ),
    )

    high = {"reason": "大额", "amount": 200, "extra": "应被清空"}
    draft = create_draft(zhangsan_client, flow["id"], high)
    assert submit(zhangsan_client, draft["id"], high).status_code == 200
    high_render = render(zhangsan_client, draft["id"]).json()
    assert "extra" not in high_render["values"]
    assert "extra" not in high_render["permissions"]

    low = {"reason": "小额", "amount": 50, "extra": "保留"}
    draft2 = create_draft(zhangsan_client, flow["id"], low)
    assert submit(zhangsan_client, draft2["id"], low).status_code == 200
    low_render = render(zhangsan_client, draft2["id"]).json()
    assert low_render["values"]["extra"] == "保留"
    assert low_render["permissions"]["extra"]["visible"] is True
