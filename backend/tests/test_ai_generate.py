"""AI 辅助配置（M15）。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import AuditLog
from app.services import ai_service

BASE = "/api/v1"

FORM_SCHEMA = {
    "model_version": 1,
    "layout": {"label_position": "top", "columns": 2},
    "sections": [{
        "key": "sec_apply",
        "title": "申请信息",
        "stage": "apply",
        "fields": [
            {"key": "reason", "label": "事由", "type": "text", "required": True},
            {"key": "amount", "label": "金额", "type": "number"},
        ],
    }],
    "rules": [],
}

FLOW_DEFINITION = {
    "model_version": 1,
    "start": {"id": "start", "type": "start", "name": "发起"},
    "steps": [{
        "id": "s1",
        "type": "approval",
        "name": "部门审批",
        "assignee": {"mode": "SINGLE", "sources": [{"type": "dept_manager"}]},
    }],
    "end": {"id": "end", "type": "end", "name": "结束"},
}


@pytest.fixture
def ai_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_rate_limit_per_hour", 20)


def _reply(content: dict) -> dict:
    return {"content": json.dumps(content, ensure_ascii=False), "usage": {"total_tokens": 10}}


def test_status_hides_when_disabled(client, designer_headers, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    resp = client.get(f"{BASE}/ai/status", headers=designer_headers)
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_generate_form(client, db, designer_headers, ai_enabled, monkeypatch):
    monkeypatch.setattr(ai_service, "_call_model", lambda messages: _reply(FORM_SCHEMA))

    resp = client.post(
        f"{BASE}/ai/form-schema",
        headers=designer_headers,
        json={"description": "做一个出差申请"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["schema_data"]["sections"][0]["key"] == "sec_apply"

    log = db.scalar(
        select(AuditLog).where(AuditLog.action == "AI_GENERATE")
    )
    assert log is not None
    assert log.detail["success"] is True
    assert log.detail["model"]


def test_generate_form_repairs_once(client, designer_headers, ai_enabled, monkeypatch):
    replies = iter([
        _reply({"sections": "not-an-array"}),
        _reply(FORM_SCHEMA),
    ])
    monkeypatch.setattr(ai_service, "_call_model", lambda messages: next(replies))

    resp = client.post(
        f"{BASE}/ai/form-schema",
        headers=designer_headers,
        json={"description": "做一个请假申请"},
    )
    assert resp.status_code == 200, resp.text


def test_generate_form_rejects_invalid(client, designer_headers, ai_enabled, monkeypatch):
    monkeypatch.setattr(ai_service, "_call_model", lambda messages: {"content": "not json"})
    resp = client.post(
        f"{BASE}/ai/form-schema",
        headers=designer_headers,
        json={"description": "坏输出"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "AI_OUTPUT_INVALID"


def test_generate_flow(client, designer_headers, ai_enabled, monkeypatch):
    monkeypatch.setattr(ai_service, "_call_model", lambda messages: _reply(FLOW_DEFINITION))

    resp = client.post(
        f"{BASE}/ai/flow-definition",
        headers=designer_headers,
        json={"description": "部门审批", "form_schema": FORM_SCHEMA},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["definition"]["steps"][0]["type"] == "approval"


def test_rate_limit(client, designer_headers, ai_enabled, monkeypatch):
    monkeypatch.setattr(settings, "ai_rate_limit_per_hour", 1)
    monkeypatch.setattr(ai_service, "_call_model", lambda messages: _reply(FORM_SCHEMA))

    first = client.post(
        f"{BASE}/ai/form-schema", headers=designer_headers,
        json={"description": "第一次"},
    )
    assert first.status_code == 200

    second = client.post(
        f"{BASE}/ai/form-schema", headers=designer_headers,
        json={"description": "第二次"},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "AI_RATE_LIMITED"


def test_disabled_returns_404(client, designer_headers, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    resp = client.post(
        f"{BASE}/ai/form-schema", headers=designer_headers,
        json={"description": "x"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "AI_DISABLED"
