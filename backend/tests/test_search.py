"""实例业务字段检索（M13）。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.constants import FormStatus, FormVersionStatus, InstanceStatus
from app.core.errors import UnprocessableError
from app.models import FlowInstance, FormSearchField, FormTemplate, FormVersion, User
from app.schemas.form_schema import parse_form_schema
from app.services import form_service, search_service
from tests.test_engine_service import _draft_instance, _published_flow, _published_form, _user

BASE = "/api/v1"

SCHEMA = {
    "sections": [
        {
            "key": "sec_apply",
            "title": "申请信息",
            "stage": "apply",
            "fields": [
                {"key": "reason", "label": "事由", "type": "text", "required": True},
                {
                    "key": "leaveType", "label": "假别", "type": "select",
                    "options": [
                        {"label": "事假", "value": "personal"},
                        {"label": "年假", "value": "annual"},
                    ],
                },
                {"key": "days", "label": "天数", "type": "number"},
                {"key": "startDate", "label": "开始日期", "type": "date"},
                {"key": "tags", "label": "标签", "type": "checkbox",
                 "options": [{"label": "紧急", "value": "urgent"},
                             {"label": "跨部门", "value": "cross"}]},
            ],
        }
    ]
}


def _setup(db, initiator):
    owner = _user(db)
    form = _published_form(db, owner)
    form.schema = SCHEMA
    db.flush()
    template = db.get(FormTemplate, form.template_id)
    template.status = FormStatus.PUBLISHED
    flow = _published_flow(db, owner, form, {"steps": []})
    return form, flow


def _instance(db, flow, form, initiator, data: dict) -> FlowInstance:
    instance = _draft_instance(db, flow, form, initiator)
    instance.status = InstanceStatus.RUNNING
    instance.current_data = data
    instance.data_schema = form.schema
    db.flush()
    return instance


def _save_fields(client, headers, template_id: int, keys: list[str]) -> None:
    resp = client.put(
        f"{BASE}/form-templates/{template_id}/search-fields",
        headers=headers,
        json={"field_keys": keys},
    )
    assert resp.status_code == 200, resp.text


def test_config_and_filter(client, db, admin_headers, normal_headers, normal_user):
    form, flow = _setup(db, normal_user)
    _save_fields(
        client, admin_headers, form.template_id,
        ["reason", "leaveType", "days", "startDate", "tags"],
    )

    configs = client.get(
        f"{BASE}/form-templates/{form.template_id}/search-fields", headers=admin_headers
    ).json()
    assert {item["field_key"] for item in configs} >= {"reason", "leaveType", "days"}
    assert all(item["selected"] for item in configs if item["field_key"] in {"reason", "days"})

    matched = _instance(
        db, flow, form, normal_user,
        {"reason": "家里有事", "leaveType": "annual", "days": 5,
         "startDate": "2026-11-01", "tags": ["urgent"]},
    )
    other = _instance(
        db, flow, form, normal_user,
        {"reason": "去看病", "leaveType": "personal", "days": 1,
         "startDate": "2026-10-01", "tags": ["cross"]},
    )
    for instance in (matched, other):
        search_service.sync_instance_index(
            db, instance=instance, form_schema=parse_form_schema(form.schema)
        )
    db.commit()

    def query(items: list[dict]) -> list[int]:
        resp = client.get(
            f"{BASE}/instances",
            headers=normal_headers,
            params={
                "scope": "mine",
                "flow_template_id": flow.template_id,
                "filters": json.dumps(items),
            },
        )
        assert resp.status_code == 200, resp.text
        return [item["id"] for item in resp.json()["items"]]

    assert query([{"field": "reason", "op": "contains", "value": "家里"}]) == [matched.id]
    assert query([{"field": "leaveType", "op": "eq", "value": "annual"}]) == [matched.id]
    assert query([{"field": "days", "op": "between", "value": [3, 10]}]) == [matched.id]
    assert query([{"field": "startDate", "op": "gte", "value": "2026-10-15"}]) == [matched.id]
    assert query([{"field": "tags", "op": "has_any", "value": ["urgent"]}]) == [matched.id]
    assert query([{"field": "tags", "op": "has_all", "value": ["urgent", "cross"]}]) == []


def test_filter_validation(client, db, admin_headers, normal_headers, normal_user):
    form, flow = _setup(db, normal_user)
    _save_fields(client, admin_headers, form.template_id, ["reason"])

    missing_template = client.get(
        f"{BASE}/instances", headers=normal_headers,
        params={"scope": "mine", "filters": json.dumps([
            {"field": "reason", "op": "eq", "value": "x"}
        ])},
    )
    assert missing_template.status_code == 422
    assert missing_template.json()["detail"]["code"] == "FLOW_TEMPLATE_REQUIRED"

    unknown = client.get(
        f"{BASE}/instances", headers=normal_headers,
        params={
            "scope": "mine",
            "flow_template_id": flow.template_id,
            "filters": json.dumps([{"field": "secret", "op": "eq", "value": "x"}]),
        },
    )
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "FILTER_FIELD_NOT_ALLOWED"


def test_publish_blocks_type_conflict(client, db, admin_headers, normal_user):
    form, _flow = _setup(db, normal_user)
    _save_fields(client, admin_headers, form.template_id, ["days"])

    template = db.get(FormTemplate, form.template_id)
    changed = dict(SCHEMA)
    changed["sections"] = [
        {
            **SCHEMA["sections"][0],
            "fields": [
                {**field, "type": "text"} if field["key"] == "days" else field
                for field in SCHEMA["sections"][0]["fields"]
            ],
        }
    ]
    version = FormVersion(
        template_id=template.id, version_no=999, schema=changed,
        status=FormVersionStatus.DRAFT, created_by=template.created_by,
    )
    db.add(version)
    db.flush()
    actor = db.scalar(select(User).where(User.id == template.created_by))

    with pytest.raises(UnprocessableError) as exc:
        form_service.publish_version(db, version, actor=actor)
    assert exc.value.code == "SEARCH_FIELD_TYPE_CONFLICT"


def test_copy_carries_search_config(client, db, admin_headers, normal_user):
    form, _flow = _setup(db, normal_user)
    _save_fields(client, admin_headers, form.template_id, ["reason", "days"])

    template = db.get(FormTemplate, form.template_id)
    actor = db.scalar(select(User).where(User.id == template.created_by))
    copied = form_service.copy_template(
        db, template, name="副本", code=None, actor=actor
    )
    keys = {
        row.field_key
        for row in db.scalars(
            select(FormSearchField).where(FormSearchField.form_template_id == copied.id)
        ).all()
    }
    assert keys == {"reason", "days"}
