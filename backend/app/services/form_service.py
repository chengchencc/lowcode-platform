"""表单模板与版本的服务层（F1.1–F1.5、F1.8）。

版本生命周期（PRD §3.1：模板改版不影响运行中的实例）：

    DRAFT ──发布──> PUBLISHED ──新版本发布时──> ARCHIVED

- 同一模板同时只允许**一个** DRAFT（编辑中的工作副本）
- 已发布的版本 `schema` 冻结，不可再改；要改就新建版本
- 流程版本发布时会锁定当时引用的表单版本，因此历史版本永不物理删除
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.constants import AuditAction, AuditBizType, FormStatus, FormVersionStatus
from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.models import FlowTemplate, FlowVersion, FormTemplate, FormVersion, User
from app.schemas.form import (
    FormTemplateCreate,
    FormTemplateUpdate,
    FormVersionCreate,
    FormVersionUpdate,
)
from app.schemas.form_schema import (
    FormSchema,
    SchemaIssue,
    has_errors,
    parse_form_schema,
    validate_form_schema,
)
from app.services import audit_service, search_service


#: 新建表单时的默认 schema —— 给一个可立即编辑的「申请信息」分区
def default_schema() -> dict[str, Any]:
    return FormSchema(
        sections=[
            {
                "key": "sec_apply",
                "title": "申请信息",
                "stage": "apply",
                "sort": 1,
                "fields": [],
            }
        ]
    ).model_dump(mode="json")


def _count_fields(schema: FormSchema) -> int:
    total = 0
    for section in schema.sections:
        for field in section.fields:
            total += 1
            total += len(field.columns)
    return total


# --------------------------------------------------------------------------- 模板


def get_or_404(db: Session, template_id: int) -> FormTemplate:
    template = db.get(FormTemplate, template_id)
    if template is None:
        raise NotFoundError("表单模板不存在", code="FORM_TEMPLATE_NOT_FOUND")
    return template


def _versions_of(db: Session, template_id: int) -> list[FormVersion]:
    return list(
        db.scalars(
            select(FormVersion)
            .where(FormVersion.template_id == template_id)
            .order_by(FormVersion.version_no.desc())
        ).all()
    )


def _to_out(db: Session, template: FormTemplate) -> dict[str, Any]:
    versions = _versions_of(db, template.id)
    published = [v for v in versions if v.status == FormVersionStatus.PUBLISHED]
    drafts = [v for v in versions if v.status == FormVersionStatus.DRAFT]

    current = next((v for v in published if v.id == template.current_version_id), None)
    if current is None and published:
        current = published[0]

    field_count = 0
    if current is not None:
        try:
            field_count = _count_fields(parse_form_schema(current.schema))
        except Exception:  # noqa: BLE001 - 历史脏数据不该让列表页 500
            field_count = 0

    return {
        "id": template.id,
        "name": template.name,
        "code": template.code,
        "group_name": template.group_name,
        "icon": template.icon,
        "status": template.status,
        "description": template.description,
        "current_version_id": current.id if current else None,
        "current_version_no": current.version_no if current else None,
        "draft_version_id": drafts[0].id if drafts else None,
        "version_count": len(versions),
        "field_count": field_count,
        "created_by": template.created_by,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def list_templates(
    db: Session,
    *,
    keyword: str | None = None,
    group_name: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(FormTemplate).order_by(FormTemplate.id.desc())
    if status:
        stmt = stmt.where(FormTemplate.status == status)
    if group_name:
        stmt = stmt.where(FormTemplate.group_name == group_name)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(FormTemplate.name.like(like) | FormTemplate.code.like(like))
    return [_to_out(db, t) for t in db.scalars(stmt).all()]


def to_out(db: Session, template: FormTemplate) -> dict[str, Any]:
    return _to_out(db, template)


def list_groups(db: Session) -> list[str]:
    rows = db.execute(
        select(FormTemplate.group_name)
        .where(FormTemplate.group_name.is_not(None))
        .group_by(FormTemplate.group_name)
        .order_by(FormTemplate.group_name)
    ).all()
    return [r[0] for r in rows if r[0]]


def _assert_code_available(
    db: Session, code: str | None, *, exclude_id: int | None = None
) -> None:
    if not code:
        return
    stmt = select(FormTemplate.id).where(FormTemplate.code == code)
    if exclude_id is not None:
        stmt = stmt.where(FormTemplate.id != exclude_id)
    if db.scalar(stmt):
        raise ConflictError(f"表单编码 {code} 已存在", code="FORM_CODE_EXISTS")


def create_template(
    db: Session,
    payload: FormTemplateCreate,
    *,
    actor: User,
    ip: str | None = None,
) -> FormTemplate:
    _assert_code_available(db, payload.code)

    # 同 update_version：新建时也允许语义不完整的 schema（例如从 JSON 导入一份待完善的表单）
    schema = payload.schema_data or FormSchema.model_validate(default_schema())

    template = FormTemplate(
        name=payload.name,
        code=payload.code,
        group_name=payload.group_name,
        icon=payload.icon,
        description=payload.description,
        status=FormStatus.DRAFT,
        created_by=actor.id,
    )
    db.add(template)
    db.flush()

    version = FormVersion(
        template_id=template.id,
        version_no=1,
        schema=schema.model_dump(mode="json"),
        status=FormVersionStatus.DRAFT,
        created_by=actor.id,
    )
    db.add(version)
    db.flush()

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FORM_TEMPLATE,
        biz_id=template.id,
        action=AuditAction.CREATE,
        summary=f"新建表单模板「{template.name}」",
        detail={"name": template.name, "code": template.code},
        ip=ip,
    )
    db.commit()
    db.refresh(template)
    return template


def update_template(
    db: Session,
    template: FormTemplate,
    payload: FormTemplateUpdate,
    *,
    actor: User,
    ip: str | None = None,
) -> FormTemplate:
    if payload.name is not None:
        template.name = payload.name
    if payload.code:
        # 编码只允许「空 → 有」补录：副本/导入件建立时故意不带编码，
        # 但没有别的入口能补，列表里会永远显示「—」。
        # 已设置后保持不可变，避免外部按编码引用时目标漂移。
        if template.code:
            if payload.code != template.code:
                raise ConflictError(
                    "表单编码设置后不可修改", code="FORM_CODE_IMMUTABLE"
                )
        else:
            _assert_code_available(db, payload.code, exclude_id=template.id)
            template.code = payload.code
    if "group_name" in payload.model_fields_set:
        template.group_name = payload.group_name
    if "icon" in payload.model_fields_set:
        template.icon = payload.icon
    if "description" in payload.model_fields_set:
        template.description = payload.description

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FORM_TEMPLATE,
        biz_id=template.id,
        action=AuditAction.UPDATE,
        summary=f"修改表单模板「{template.name}」",
        detail={"name": template.name, "code": template.code},
        ip=ip,
    )
    db.commit()
    db.refresh(template)
    return template


def set_template_status(
    db: Session,
    template: FormTemplate,
    status: FormStatus,
    *,
    actor: User,
    ip: str | None = None,
) -> FormTemplate:
    if status == FormStatus.PUBLISHED:
        raise UnprocessableError(
            "启用状态由发布版本自动决定，不能手工设置",
            code="STATUS_MANAGED_BY_PUBLISH",
        )

    template.status = status
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FORM_TEMPLATE,
        biz_id=template.id,
        action=AuditAction.DISABLE if status == FormStatus.DISABLED else AuditAction.ENABLE,
        summary=f"{'停用' if status == FormStatus.DISABLED else '草稿化'}表单模板「{template.name}」",
        ip=ip,
    )
    db.commit()
    db.refresh(template)
    return template


def delete_template(
    db: Session, template: FormTemplate, *, actor: User, ip: str | None = None
) -> None:
    """删除模板（连同全部版本）。

    **被流程版本锁定时拒绝删除**：`flow_versions.locked_form_version_id` 指向这些
    版本，硬删会撞外键；语义上也该拒绝 —— 运行中的实例要按锁定的 schema 渲染，
    模板没了就渲染不出来。要停止使用请改为「停用」。
    """
    referencing = list(
        db.scalars(
            select(FlowVersion.template_id)
            .join(FlowTemplate, FlowTemplate.id == FlowVersion.template_id)
            .where(FlowVersion.locked_form_version_id.in_(select(FormVersion.id).where(
                FormVersion.template_id == template.id
            )))
        ).all()
    )
    if referencing:
        raise ConflictError(
            f"该表单已被 {len(set(referencing))} 个流程模板引用（发布时锁定了它的版本），"
            "不能删除。如需停止使用，请改为「停用」。",
            code="FORM_REFERENCED_BY_FLOW",
            extra={"flow_template_ids": sorted(set(referencing))},
        )

    biz_id, name = template.id, template.name
    db.delete(template)  # versions 走 cascade="all, delete-orphan"
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FORM_TEMPLATE,
        biz_id=biz_id,
        action=AuditAction.DELETE,
        summary=f"删除表单模板「{name}」",
        ip=ip,
    )
    db.commit()


def copy_template(
    db: Session,
    template: FormTemplate,
    *,
    name: str,
    code: str | None,
    actor: User,
    ip: str | None = None,
) -> FormTemplate:
    """复制模板（F1.8）。复制最新 PUBLISHED 版本的 schema，没有则用 DRAFT。"""
    _assert_code_available(db, code)

    source = _current_version(db, template) or (_versions_of(db, template.id) or [None])[0]

    copy = FormTemplate(
        name=name,
        code=code,
        group_name=template.group_name,
        icon=template.icon,
        description=template.description,
        status=FormStatus.DRAFT,
        created_by=actor.id,
    )
    db.add(copy)
    db.flush()

    schema = source.schema if source else default_schema()
    version = FormVersion(
        template_id=copy.id,
        version_no=1,
        schema=schema,
        status=FormVersionStatus.DRAFT,
        remark=f"复制自「{template.name}」",
        created_by=actor.id,
    )
    db.add(version)
    db.flush()
    # 副本沿用源模板的可检索配置；索引由新实例提交时自然产生
    search_service.copy_configs(db, template.id, copy.id, actor.id)

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FORM_TEMPLATE,
        biz_id=copy.id,
        action=AuditAction.COPY,
        summary=f"复制表单模板「{template.name}」→「{name}」",
        ip=ip,
    )
    db.commit()
    db.refresh(copy)
    return copy


def export_template(db: Session, template: FormTemplate) -> dict[str, Any]:
    """导出为可迁移的 JSON（F1.8）。只导出最新版本，不带 id 等本地标识。"""
    version = _current_version(db, template)
    if version is None:
        versions = _versions_of(db, template.id)
        version = versions[0] if versions else None
    # 键名与导入接口的入参保持一致（schema_data），导出的 JSON 可直接回传导入
    return {
        "name": template.name,
        "code": template.code,
        "group_name": template.group_name,
        "description": template.description,
        "schema_data": version.schema if version else default_schema(),
    }


# --------------------------------------------------------------------------- 版本


def _current_version(db: Session, template: FormTemplate) -> FormVersion | None:
    """当前生效版本：优先 current_version_id 指向的，否则最新 PUBLISHED。"""
    if template.current_version_id is not None:
        version = db.get(FormVersion, template.current_version_id)
        if version is not None and version.status == FormVersionStatus.PUBLISHED:
            return version
    return db.scalar(
        select(FormVersion)
        .where(
            FormVersion.template_id == template.id,
            FormVersion.status == FormVersionStatus.PUBLISHED,
        )
        .order_by(FormVersion.version_no.desc())
        .limit(1)
    )


def get_version_or_404(db: Session, version_id: int) -> FormVersion:
    version = db.get(FormVersion, version_id)
    if version is None:
        raise NotFoundError("表单版本不存在", code="FORM_VERSION_NOT_FOUND")
    return version


def list_versions(db: Session, template: FormTemplate) -> list[FormVersion]:
    return _versions_of(db, template.id)


def version_to_out(db: Session, version: FormVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "template_id": version.template_id,
        "version_no": version.version_no,
        "status": version.status,
        "remark": version.remark,
        "created_by": version.created_by,
        "published_at": version.published_at,
        "created_at": version.created_at,
        "schema_data": version.schema,
        # M3：流程版本发布时锁定的表单版本
        "referenced_by_flows": [],
    }


def create_version(
    db: Session,
    template: FormTemplate,
    payload: FormVersionCreate,
    *,
    actor: User,
    ip: str | None = None,
) -> FormVersion:
    """新建 DRAFT 版本。已存在 DRAFT 时直接复用并返回它（幂等）。"""
    existing_draft = db.scalar(
        select(FormVersion).where(
            FormVersion.template_id == template.id,
            FormVersion.status == FormVersionStatus.DRAFT,
        )
    )
    if existing_draft is not None:
        return existing_draft

    base_schema: dict[str, Any]
    if payload.from_version_id is not None:
        base = get_version_or_404(db, payload.from_version_id)
        if base.template_id != template.id:
            raise NotFoundError("该版本不属于此表单模板", code="FORM_VERSION_MISMATCH")
        base_schema = base.schema
    else:
        current = _current_version(db, template)
        if current is not None:
            base_schema = current.schema
        else:
            versions = _versions_of(db, template.id)
            base_schema = versions[0].schema if versions else default_schema()

    next_no = (
        db.scalar(
            select(func.max(FormVersion.version_no)).where(
                FormVersion.template_id == template.id
            )
        )
        or 0
    ) + 1

    version = FormVersion(
        template_id=template.id,
        version_no=next_no,
        schema=base_schema,
        status=FormVersionStatus.DRAFT,
        remark=payload.remark,
        created_by=actor.id,
    )
    db.add(version)
    db.flush()

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FORM_TEMPLATE,
        biz_id=template.id,
        action=AuditAction.CREATE,
        summary=f"「{template.name}」新建草稿版本 v{next_no}",
        detail={"version_id": version.id, "from_version_id": payload.from_version_id},
        ip=ip,
    )
    db.commit()
    db.refresh(version)
    return version


def update_version(
    db: Session,
    version: FormVersion,
    payload: FormVersionUpdate,
    *,
    actor: User,
    ip: str | None = None,
) -> FormVersion:
    """保存草稿版本。

    **刻意不做语义校验**：设计器需要能存下「还没配完」的表单 ——
    比如刚拖入一个单选控件、还没来得及填选项，或者公式引用的字段准备下一步再建。
    如果保存时就卡死，设计器每次自动保存都会被拒，根本没法用。

    形状合法性（类型、必填字段结构）由 pydantic 在请求解析阶段保证；
    语义问题（选项为空、公式引用不存在的字段…）留到 `publish_version` 时拦。
    """
    if version.status != FormVersionStatus.DRAFT:
        raise UnprocessableError(
            f"v{version.version_no} 已发布，不能再修改；请新建版本",
            code="VERSION_NOT_EDITABLE",
        )

    version.schema = payload.schema_data.model_dump(mode="json")
    if payload.remark is not None:
        version.remark = payload.remark

    db.commit()
    db.refresh(version)
    return version


def validate_version(db: Session, version: FormVersion) -> list[SchemaIssue]:
    try:
        schema = parse_form_schema(version.schema)
    except Exception as exc:  # noqa: BLE001
        return [
            SchemaIssue(
                code="SCHEMA_MALFORMED",
                message=f"版本结构无法解析：{exc}",
                path="",
            )
        ]
    return validate_form_schema(schema)


def publish_version(
    db: Session,
    version: FormVersion,
    *,
    actor: User,
    remark: str | None = None,
    ip: str | None = None,
) -> FormVersion:
    """发布版本（F1.5）：校验通过后冻结，并把上一个 PUBLISHED 归档。"""
    if version.status == FormVersionStatus.PUBLISHED:
        raise ConflictError(f"v{version.version_no} 已经是发布状态", code="ALREADY_PUBLISHED")
    if version.status == FormVersionStatus.ARCHIVED:
        raise UnprocessableError(
            f"v{version.version_no} 已归档，不能重新发布", code="VERSION_ARCHIVED"
        )

    issues = validate_version(db, version)
    if has_errors(issues):
        raise UnprocessableError(
            "表单结构校验未通过，无法发布",
            code="FORM_SCHEMA_INVALID",
            extra={"errors": [i.model_dump() for i in issues if i.severity == "error"]},
        )

    # 可检索字段跨版本类型冲突会破坏索引语义，发布前拦下
    search_service.assert_publish_consistency(
        db, version.template_id, parse_form_schema(version.schema)
    )

    # 归档上一个已发布版本：历史实例仍按它自己的快照渲染，不受影响
    for previous in db.scalars(
        select(FormVersion).where(
            FormVersion.template_id == version.template_id,
            FormVersion.status == FormVersionStatus.PUBLISHED,
        )
    ).all():
        previous.status = FormVersionStatus.ARCHIVED

    version.status = FormVersionStatus.PUBLISHED
    version.published_at = utcnow()
    if remark:
        version.remark = remark

    template = db.get(FormTemplate, version.template_id)
    if template is not None:
        template.current_version_id = version.id
        if template.status == FormStatus.DRAFT:
            template.status = FormStatus.PUBLISHED

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FORM_TEMPLATE,
        biz_id=version.template_id,
        action=AuditAction.PUBLISH,
        summary=f"发布表单版本 v{version.version_no}",
        detail={"version_id": version.id, "version_no": version.version_no},
        ip=ip,
    )
    db.commit()
    db.refresh(version)
    return version


def delete_version(
    db: Session, version: FormVersion, *, actor: User, ip: str | None = None
) -> None:
    """仅允许删除未发布的草稿（PRD F1.5：被流程引用的版本不可物理删除）。"""
    if version.status != FormVersionStatus.DRAFT:
        raise UnprocessableError(
            f"v{version.version_no} 是{_status_label(version.status)}，不能删除",
            code="VERSION_NOT_DELETABLE",
        )

    template_id, version_no = version.template_id, version.version_no
    db.delete(version)
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FORM_TEMPLATE,
        biz_id=template_id,
        action=AuditAction.DELETE,
        summary=f"删除草稿版本 v{version_no}",
        ip=ip,
    )
    db.commit()


def _status_label(status: str) -> str:
    return {
        FormVersionStatus.PUBLISHED: "已发布版本",
        FormVersionStatus.ARCHIVED: "已归档版本",
    }.get(status, status)
