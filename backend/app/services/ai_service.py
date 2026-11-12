"""AI 辅助配置（M15）。

只做配置生成，不自动保存/发布；只发送业务描述与 schema 结构，
不发送实例数据。出网地址由后端配置固定。
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import timedelta
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.core.constants import AuditAction, AuditBizType
from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.engine.validate import validate_flow_definition
from app.models import AuditLog, User
from app.schemas.flow_definition import FlowDefinition
from app.schemas.form_schema import FormSchema, validate_form_schema
from app.services import audit_service

FIELD_TYPES = (
    "text, textarea, number, radio, checkbox, select, date, time, datetime, switch, "
    "user, user_multi, dept, dept_multi, attachment, image, subtable, formula, "
    "cascader, heading, paragraph, divider, image_view, rich_text"
)

FORM_EXAMPLE = {
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
    "title_field": "reason",
}

FLOW_EXAMPLE = {
    "model_version": 1,
    "start": {"id": "start", "type": "start", "name": "发起"},
    "steps": [{
        "id": "s1",
        "type": "approval",
        "name": "部门审批",
        "assignee": {"mode": "SINGLE", "sources": [{"type": "dept_manager"}]},
        "reject_policy": "reject_to_initiator",
        "return_targets": None,
        "timeout_hours": None,
        "opinion_required": False,
        "attachment_required": False,
        "fields_permission": {
            "base": "readonly",
            "partitions": {},
            "overrides": {},
            "conditional_overrides": [],
        },
    }],
    "end": {"id": "end", "type": "end", "name": "结束"},
}


def status() -> dict[str, Any]:
    return {
        "enabled": bool(settings.ai_enabled and settings.ai_api_key),
        "model": settings.ai_model if settings.ai_enabled else None,
    }


def _assert_enabled() -> None:
    if not settings.ai_enabled or not settings.ai_api_key:
        raise NotFoundError("AI 功能未开启", code="AI_DISABLED")


def _assert_rate_limit(db: Session, actor: User) -> None:
    since = utcnow() - timedelta(hours=1)
    count = db.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.actor_id == actor.id,
            AuditLog.biz_type == AuditBizType.AI,
            AuditLog.action == AuditAction.AI_GENERATE,
            AuditLog.created_at >= since,
        )
    ) or 0
    if count >= settings.ai_rate_limit_per_hour:
        raise ConflictError("AI 生成次数已达上限，请稍后再试", code="AI_RATE_LIMITED")


def _call_model(messages: list[dict[str, str]]) -> dict[str, Any]:
    """OpenAI 兼容 chat completions。测试通过 monkeypatch 替换本函数。"""
    assert settings.ai_api_key is not None
    url = settings.ai_base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": settings.ai_model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": settings.ai_max_tokens,
        "response_format": {"type": "json_object"},
    }
    try:
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.ai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.ai_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise UnprocessableError(
            f"AI 服务调用失败：{exc.__class__.__name__}", code="AI_UPSTREAM_ERROR"
        ) from exc
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise UnprocessableError("AI 返回格式异常", code="AI_UPSTREAM_ERROR") from exc
    return {"content": content, "usage": data.get("usage") or {}}


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        cleaned = cleaned.rsplit("```", 1)[0]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise UnprocessableError("AI 没有返回 JSON", code="AI_OUTPUT_INVALID")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise UnprocessableError("AI 返回的 JSON 无法解析", code="AI_OUTPUT_INVALID") from exc


def _audit(
    db: Session,
    *,
    actor: User,
    kind: str,
    prompt: str,
    started: float,
    success: bool,
    usage: dict[str, Any] | None = None,
    error: str | None = None,
    ip: str | None = None,
) -> None:
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.AI,
        biz_id=0,
        action=AuditAction.AI_GENERATE,
        summary=f"AI 生成{kind}",
        detail={
            "kind": kind,
            "model": settings.ai_model,
            "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:32],
            "duration_ms": int((time.monotonic() - started) * 1000),
            "usage": usage or {},
            "success": success,
            "error": error,
        },
        ip=ip,
    )
    db.commit()


def _repair_messages(
    messages: list[dict[str, str]], raw: str, error: str
) -> list[dict[str, str]]:
    return [
        *messages,
        {"role": "assistant", "content": raw},
        {
            "role": "user",
            "content": (
                "上面的输出没有通过校验。错误如下：\n"
                f"{error[:3000]}\n"
                "请只返回修正后的完整 JSON，不要解释。"
            ),
        },
    ]


def _form_messages(description: str, preferences: str | None) -> list[dict[str, str]]:
    system = (
        "你是企业低代码平台的表单配置助手。把业务描述转换成 FormSchema JSON。"
        f"允许的字段类型：{FIELD_TYPES}。"
        "展示型控件（heading/paragraph/divider/image_view/rich_text）不绑定数据，"
        "不能作为公式/条件字段。字段 key 用英文小驼峰且唯一。"
        "只输出 JSON 对象，不要输出 Markdown 或解释。"
        f"示例结构：{json.dumps(FORM_EXAMPLE, ensure_ascii=False)}"
    )
    user = f"业务描述：{description}"
    if preferences:
        user += f"\n配置偏好：{preferences}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _flow_messages(description: str, form_schema: dict[str, Any]) -> list[dict[str, str]]:
    fields = []
    for section in form_schema.get("sections", []):
        for field in section.get("fields", []):
            fields.append({
                "key": field.get("key"),
                "label": field.get("label"),
                "type": field.get("type"),
            })
    system = (
        "你是企业低代码平台的流程配置助手。把业务描述转换成 FlowDefinition JSON。"
        "节点类型只能用 approval/fill/condition/parallel/cc。"
        "审批人来源 type 只能用 dept_manager/form_user_field/form_dept_field/"
        "role/user/initiator_select/prev_node_actors；"
        "没有具体 id 时优先用 dept_manager，或引用表单里的人员/部门字段。"
        "条件字段必须来自给定的表单字段。id 全局唯一。"
        "只输出 JSON 对象，不要输出 Markdown 或解释。"
        f"示例结构：{json.dumps(FLOW_EXAMPLE, ensure_ascii=False)}"
    )
    user = (
        f"业务描述：{description}\n"
        f"表单字段：{json.dumps(fields, ensure_ascii=False)}\n"
        f"完整表单 schema：{json.dumps(form_schema, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _validate_form(data: Any) -> tuple[dict[str, Any], str | None]:
    try:
        schema = FormSchema.model_validate(data)
    except ValidationError as exc:
        return {}, str(exc)
    issues = [issue for issue in validate_form_schema(schema) if issue.severity == "error"]
    if issues:
        return {}, "\n".join(f"{issue.path}: {issue.message}" for issue in issues)
    return schema.model_dump(mode="json"), None


def _validate_flow(
    data: Any, form_schema: dict[str, Any]
) -> tuple[dict[str, Any], str | None]:
    try:
        definition = FlowDefinition.model_validate(data)
    except ValidationError as exc:
        return {}, str(exc)
    issues = [
        issue for issue in validate_flow_definition(definition, form_schema)
        if issue.severity == "error"
    ]
    if issues:
        return {}, "\n".join(f"{issue.path}: {issue.message}" for issue in issues)
    return definition.model_dump(mode="json"), None


def generate_form_schema(
    db: Session,
    *,
    actor: User,
    description: str,
    preferences: str | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    _assert_enabled()
    _assert_rate_limit(db, actor)
    started = time.monotonic()
    messages = _form_messages(description, preferences)
    prompt = json.dumps(messages, ensure_ascii=False)
    usage: dict[str, Any] = {}
    try:
        response = _call_model(messages)
        usage = response.get("usage") or {}
        data, error = _validate_form(_extract_json(response["content"]))
        if error:
            repaired = _call_model(_repair_messages(messages, response["content"], error))
            usage = repaired.get("usage") or usage
            data, error = _validate_form(_extract_json(repaired["content"]))
        if error:
            raise UnprocessableError(
                f"AI 生成的表单未通过校验：{error[:500]}", code="AI_OUTPUT_INVALID"
            )
        _audit(db, actor=actor, kind="表单", prompt=prompt, started=started,
               success=True, usage=usage, ip=ip)
        return {"schema_data": data}
    except Exception as exc:
        db.rollback()
        _audit(db, actor=actor, kind="表单", prompt=prompt, started=started,
               success=False, usage=usage, error=str(exc)[:500], ip=ip)
        raise


def generate_flow_definition(
    db: Session,
    *,
    actor: User,
    description: str,
    form_schema: dict[str, Any],
    ip: str | None = None,
) -> dict[str, Any]:
    _assert_enabled()
    _assert_rate_limit(db, actor)
    started = time.monotonic()
    messages = _flow_messages(description, form_schema)
    prompt = json.dumps(messages, ensure_ascii=False)
    usage: dict[str, Any] = {}
    try:
        response = _call_model(messages)
        usage = response.get("usage") or {}
        data, error = _validate_flow(_extract_json(response["content"]), form_schema)
        if error:
            repaired = _call_model(_repair_messages(messages, response["content"], error))
            usage = repaired.get("usage") or usage
            data, error = _validate_flow(_extract_json(repaired["content"]), form_schema)
        if error:
            raise UnprocessableError(
                f"AI 生成的流程未通过校验：{error[:500]}", code="AI_OUTPUT_INVALID"
            )
        _audit(db, actor=actor, kind="流程", prompt=prompt, started=started,
               success=True, usage=usage, ip=ip)
        return {"definition": data}
    except Exception as exc:
        db.rollback()
        _audit(db, actor=actor, kind="流程", prompt=prompt, started=started,
               success=False, usage=usage, error=str(exc)[:500], ip=ip)
        raise
