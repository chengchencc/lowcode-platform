"""AI 辅助配置接口（M15）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import ClientIp, DbSession, DesignerUser
from app.schemas.ai import (
    AiFlowRequest,
    AiFlowResponse,
    AiFormRequest,
    AiFormResponse,
    AiStatusOut,
)
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["AI"])


@router.get("/status", response_model=AiStatusOut, summary="AI 是否可用")
def status(_: DesignerUser) -> dict:
    return ai_service.status()


@router.post("/form-schema", response_model=AiFormResponse, summary="生成表单草稿")
def generate_form(
    payload: AiFormRequest,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    return ai_service.generate_form_schema(
        db,
        actor=actor,
        description=payload.description,
        preferences=payload.preferences,
        ip=ip,
    )


@router.post("/flow-definition", response_model=AiFlowResponse, summary="生成流程草稿")
def generate_flow(
    payload: AiFlowRequest,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    return ai_service.generate_flow_definition(
        db,
        actor=actor,
        description=payload.description,
        form_schema=payload.form_schema,
        ip=ip,
    )
