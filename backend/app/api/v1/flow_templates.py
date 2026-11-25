"""流程模板接口（F2.1 / F2.5 / F2.6）。

全部要求设计者权限（PRD §5「审批管理」栏目）。
发起人侧读取可发起流程的接口在 M4，权限模型不同。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import ClientIp, DbSession, DesignerUser
from app.schemas.common import OkResp
from app.schemas.flow import (
    FlowTemplateCreate,
    FlowTemplateImport,
    FlowTemplateOut,
    FlowTemplateStatusRequest,
    FlowTemplateUpdate,
    FlowVersionBrief,
)
from app.services import flow_service

router = APIRouter(prefix="/flow-templates", tags=["流程模板"])


@router.get("", response_model=list[FlowTemplateOut], summary="流程模板列表")
def list_templates(
    db: DbSession,
    _: DesignerUser,
    keyword: Annotated[str | None, Query(description="名称/编码模糊匹配")] = None,
    category: Annotated[str | None, Query()] = None,
    template_status: Annotated[str | None, Query(alias="status")] = None,
    form_template_id: Annotated[int | None, Query(description="按绑定的表单筛选")] = None,
) -> list[dict]:
    return flow_service.list_templates(
        db,
        keyword=keyword,
        category=category,
        status=template_status,
        form_template_id=form_template_id,
    )


@router.post(
    "",
    response_model=FlowTemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建流程模板",
)
def create_template(
    payload: FlowTemplateCreate, db: DbSession, actor: DesignerUser, ip: ClientIp
) -> dict:
    template = flow_service.create_template(
        db,
        name=payload.name,
        form_template_id=payload.form_template_id,
        code=payload.code,
        category=payload.category,
        description=payload.description,
        initiator_scope=payload.initiator_scope.model_dump() if payload.initiator_scope else None,
        actor=actor,
        ip=ip,
    )
    return flow_service.to_out(db, template)


@router.post(
    "/import",
    response_model=FlowTemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="从 JSON 导入（导入为草稿）",
)
def import_template(
    payload: FlowTemplateImport, db: DbSession, actor: DesignerUser, ip: ClientIp
) -> dict:
    template = flow_service.import_template(
        db,
        name=payload.name or "导入的流程",
        form_template_id=payload.form_template_id,
        code=payload.code,
        category=payload.category,
        description=payload.description,
        initiator_scope=payload.initiator_scope.model_dump() if payload.initiator_scope else None,
        definition=payload.definition.model_dump(mode="json"),
        actor=actor,
        ip=ip,
    )
    return flow_service.to_out(db, template)


@router.get("/{template_id}", response_model=FlowTemplateOut, summary="流程模板详情")
def get_template(template_id: int, db: DbSession, _: DesignerUser) -> dict:
    return flow_service.to_out(db, flow_service.get_or_404(db, template_id))


@router.get("/{template_id}/export", summary="导出为 JSON")
def export_template(template_id: int, db: DbSession, _: DesignerUser) -> dict:
    return flow_service.export_template(db, flow_service.get_or_404(db, template_id))


@router.put("/{template_id}", response_model=FlowTemplateOut, summary="修改流程模板")
def update_template(
    template_id: int,
    payload: FlowTemplateUpdate,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    template = flow_service.update_template(
        db,
        flow_service.get_or_404(db, template_id),
        name=payload.name,
        category=payload.category,
        description=payload.description,
        initiator_scope=payload.initiator_scope.model_dump() if payload.initiator_scope else None,
        actor=actor,
        ip=ip,
    )
    return flow_service.to_out(db, template)


@router.post("/{template_id}/status", response_model=FlowTemplateOut, summary="启用 / 停用")
def set_status(
    template_id: int,
    payload: FlowTemplateStatusRequest,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    template = flow_service.set_template_status(
        db, flow_service.get_or_404(db, template_id), payload.status, actor=actor, ip=ip
    )
    return flow_service.to_out(db, template)


@router.delete("/{template_id}", response_model=OkResp, summary="删除流程模板")
def delete_template(
    template_id: int, db: DbSession, actor: DesignerUser, ip: ClientIp
) -> OkResp:
    flow_service.delete_template(
        db, flow_service.get_or_404(db, template_id), actor=actor, ip=ip
    )
    return OkResp(message="流程模板已删除")


# --------------------------------------------------------------------------- 版本


@router.get(
    "/{template_id}/versions", response_model=list[FlowVersionBrief], summary="版本列表"
)
def list_versions(template_id: int, db: DbSession, _: DesignerUser) -> list[dict]:
    template = flow_service.get_or_404(db, template_id)
    return [flow_service.version_to_out(db, v) for v in flow_service.list_versions(db, template)]


@router.post(
    "/{template_id}/versions",
    status_code=status.HTTP_201_CREATED,
    summary="新建草稿版本（已存在草稿则复用）",
)
def create_version(
    template_id: int, db: DbSession, actor: DesignerUser, ip: ClientIp
) -> dict:
    template = flow_service.get_or_404(db, template_id)
    version = flow_service.create_version(
        db, template, from_version_id=None, actor=actor, ip=ip
    )
    return flow_service.version_to_out(db, version)
