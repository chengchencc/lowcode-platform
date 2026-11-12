"""表单模板接口（F1.1 / F1.5 / F1.8）。

全部要求设计者权限（PRD §5「审批管理」栏目）。
发起人侧读取表单的接口在 M4 的实例模块，权限模型不同。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import ClientIp, DbSession, DesignerUser
from app.schemas.common import OkResp
from app.schemas.form import (
    FormTemplateCopy,
    FormTemplateCreate,
    FormTemplateImport,
    FormTemplateOut,
    FormTemplateStatusRequest,
    FormTemplateUpdate,
    FormVersionBrief,
    FormVersionCreate,
)
from app.schemas.search import (
    SearchFieldOut,
    SearchFieldSaveRequest,
    SearchFieldSaveResult,
    SearchRebuildResult,
)
from app.services import form_service

router = APIRouter(prefix="/form-templates", tags=["表单模板"])


@router.get("", response_model=list[FormTemplateOut], summary="表单模板列表")
def list_templates(
    db: DbSession,
    _: DesignerUser,
    keyword: Annotated[str | None, Query(description="名称/编码模糊匹配")] = None,
    group_name: Annotated[str | None, Query(description="分组筛选")] = None,
    template_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[dict]:
    return form_service.list_templates(
        db, keyword=keyword, group_name=group_name, status=template_status
    )


@router.get("/groups", response_model=list[str], summary="已有分组")
def list_groups(db: DbSession, _: DesignerUser) -> list[str]:
    """列表页的分组筛选下拉。必须声明在 /{template_id} 之前。"""
    return form_service.list_groups(db)


@router.post(
    "", response_model=FormTemplateOut, status_code=status.HTTP_201_CREATED, summary="新建表单模板"
)
def create_template(
    payload: FormTemplateCreate, db: DbSession, actor: DesignerUser, ip: ClientIp
) -> dict:
    template = form_service.create_template(db, payload, actor=actor, ip=ip)
    return form_service.to_out(db, template)


@router.post(
    "/import",
    response_model=FormTemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="从 JSON 导入",
)
def import_template(
    payload: FormTemplateImport, db: DbSession, actor: DesignerUser, ip: ClientIp
) -> dict:
    template = form_service.create_template(
        db,
        FormTemplateCreate(
            name=payload.name or "导入的表单",
            code=payload.code,
            group_name=payload.group_name,
            description=payload.description,
            schema_data=payload.schema_data,
        ),
        actor=actor,
        ip=ip,
    )
    return form_service.to_out(db, template)


@router.get("/{template_id}", response_model=FormTemplateOut, summary="模板详情")
def get_template(template_id: int, db: DbSession, _: DesignerUser) -> dict:
    return form_service.to_out(db, form_service.get_or_404(db, template_id))


@router.put("/{template_id}", response_model=FormTemplateOut, summary="修改模板元信息")
def update_template(
    template_id: int,
    payload: FormTemplateUpdate,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    template = form_service.update_template(
        db, form_service.get_or_404(db, template_id), payload, actor=actor, ip=ip
    )
    return form_service.to_out(db, template)


@router.post("/{template_id}/status", response_model=FormTemplateOut, summary="启用 / 停用")
def set_status(
    template_id: int,
    payload: FormTemplateStatusRequest,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    template = form_service.set_template_status(
        db, form_service.get_or_404(db, template_id), payload.status, actor=actor, ip=ip
    )
    return form_service.to_out(db, template)


@router.post(
    "/{template_id}/copy",
    response_model=FormTemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="复制模板",
)
def copy_template(
    template_id: int,
    payload: FormTemplateCopy,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    template = form_service.copy_template(
        db,
        form_service.get_or_404(db, template_id),
        name=payload.name,
        code=payload.code,
        actor=actor,
        ip=ip,
    )
    return form_service.to_out(db, template)


@router.get(
    "/{template_id}/search-fields",
    response_model=list[SearchFieldOut],
    summary="可检索字段配置（M13）",
)
def list_search_fields(template_id: int, db: DbSession, _: DesignerUser) -> list[dict]:
    from app.services import form_service, search_service

    template = form_service.get_or_404(db, template_id)
    return search_service.list_search_fields(db, template)


@router.put(
    "/{template_id}/search-fields",
    response_model=SearchFieldSaveResult,
    summary="保存可检索字段配置（M13）",
)
def save_search_fields(
    template_id: int,
    payload: SearchFieldSaveRequest,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    from app.core.constants import AuditAction, AuditBizType
    from app.services import audit_service, form_service, search_service

    template = form_service.get_or_404(db, template_id)
    result = search_service.save_search_fields(
        db, template, payload.field_keys, actor_id=actor.id
    )
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FORM_TEMPLATE,
        biz_id=template.id,
        action=AuditAction.UPDATE,
        summary=f"更新表单「{template.name}」可检索字段",
        detail={"field_keys": payload.field_keys},
        ip=ip,
    )
    db.commit()
    return result


@router.post(
    "/{template_id}/search-fields/rebuild",
    response_model=SearchRebuildResult,
    summary="重建该表单的检索索引（M13）",
)
def rebuild_search_index(
    template_id: int,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    from app.core.constants import AuditAction, AuditBizType
    from app.services import audit_service, form_service, search_service

    template = form_service.get_or_404(db, template_id)
    result = search_service.rebuild_template_index(db, template.id)
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FORM_TEMPLATE,
        biz_id=template.id,
        action=AuditAction.UPDATE,
        summary=f"重建表单「{template.name}」检索索引",
        detail=result,
        ip=ip,
    )
    db.commit()
    return result


@router.get("/{template_id}/export", summary="导出为 JSON")
def export_template(template_id: int, db: DbSession, _: DesignerUser) -> dict:
    return form_service.export_template(db, form_service.get_or_404(db, template_id))


@router.delete("/{template_id}", response_model=OkResp, summary="删除模板")
def delete_template(
    template_id: int, db: DbSession, actor: DesignerUser, ip: ClientIp
) -> OkResp:
    form_service.delete_template(
        db, form_service.get_or_404(db, template_id), actor=actor, ip=ip
    )
    return OkResp(message="表单模板已删除")


# --------------------------------------------------------------------------- 版本


@router.get(
    "/{template_id}/versions", response_model=list[FormVersionBrief], summary="版本列表"
)
def list_versions(template_id: int, db: DbSession, _: DesignerUser) -> list[dict]:
    template = form_service.get_or_404(db, template_id)
    return [
        form_service.version_to_out(db, v) for v in form_service.list_versions(db, template)
    ]


@router.post(
    "/{template_id}/versions",
    summary="新建草稿版本（已存在草稿则复用）",
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    template_id: int,
    payload: FormVersionCreate,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    template = form_service.get_or_404(db, template_id)
    version = form_service.create_version(db, template, payload, actor=actor, ip=ip)
    return form_service.version_to_out(db, version)
