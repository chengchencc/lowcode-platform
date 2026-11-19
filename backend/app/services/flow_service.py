"""流程模板与版本的服务层（F2.1–F2.8）。

与 form_service 同构的版本生命周期，但多一条关键规则：

    **发布流程版本时锁定表单版本**（PRD F2.6）

实例运行期间模板改版不影响已有实例 —— 靠的就是这个锁定。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.constants import (
    AuditAction,
    AuditBizType,
    FlowStatus,
    FlowVersionStatus,
    FormStatus,
)
from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.engine.validate import ValidationIssue, has_errors, validate_flow_definition
from app.models import (
    Department,
    FlowInstance,
    FlowTemplate,
    FlowVersion,
    FormTemplate,
    FormVersion,
    User,
)
from app.schemas.flow_definition import FlowDefinition
from app.schemas.form_schema import parse_form_schema
from app.services import audit_service, form_service


def default_definition() -> dict[str, Any]:
    """新建流程时的默认定义：一个「部门经理审批」节点，开箱即可发布试跑。"""
    return FlowDefinition.model_validate(
        {
            "steps": [
                {
                    "id": "s1",
                    "type": "approval",
                    "name": "部门经理审批",
                    "assignee": {"mode": "SINGLE", "sources": [{"type": "dept_manager"}]},
                }
            ]
        }
    ).model_dump(mode="json")


# --------------------------------------------------------------------------- 模板


def get_or_404(db: Session, template_id: int) -> FlowTemplate:
    template = db.get(FlowTemplate, template_id)
    if template is None:
        raise NotFoundError("流程模板不存在", code="FLOW_TEMPLATE_NOT_FOUND")
    return template


def _versions_of(db: Session, template_id: int) -> list[FlowVersion]:
    return list(
        db.scalars(
            select(FlowVersion)
            .where(FlowVersion.template_id == template_id)
            .order_by(FlowVersion.version_no.desc())
        ).all()
    )


def _to_out(db: Session, template: FlowTemplate) -> dict[str, Any]:
    versions = _versions_of(db, template.id)
    published = [v for v in versions if v.status == FlowVersionStatus.PUBLISHED]
    drafts = [v for v in versions if v.status == FlowVersionStatus.DRAFT]

    current = next((v for v in published if v.id == template.current_version_id), None)
    if current is None and published:
        current = published[0]

    form_template = db.get(FormTemplate, template.form_template_id)
    form_version = None
    if current is not None:
        form_version = db.get(FormVersion, current.locked_form_version_id)

    # 节点数按「当前生效版本」算；还没发布过就退回到草稿 ——
    # 否则设计器里配了半天的流程在列表页显示 0 个节点，很容易误以为没保存上
    node_source = current or (drafts[0] if drafts else None)

    return {
        "id": template.id,
        "name": template.name,
        "code": template.code,
        "category": template.category,
        "description": template.description,
        "status": template.status,
        "form_template_id": template.form_template_id,
        "form_template_name": form_template.name if form_template else None,
        "initiator_scope": template.initiator_scope,
        "current_version_id": current.id if current else None,
        "current_version_no": current.version_no if current else None,
        "locked_form_version_id": current.locked_form_version_id if current else None,
        "locked_form_version_no": form_version.version_no if form_version else None,
        "draft_version_id": drafts[0].id if drafts else None,
        "version_count": len(versions),
        "node_count": _count_nodes(node_source.definition) if node_source else 0,
        "created_by": template.created_by,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def _count_nodes(definition: dict[str, Any]) -> int:
    from app.schemas.flow_definition import iter_steps

    try:
        parsed = FlowDefinition.model_validate(definition)
    except Exception:  # noqa: BLE001 - 历史脏数据不该让列表页 500
        return 0
    # 条件节点与并行容器本身不算「审批节点」
    return sum(1 for s in iter_steps(parsed.steps) if s.type in {"approval", "fill", "cc"})


def list_templates(
    db: Session,
    *,
    keyword: str | None = None,
    category: str | None = None,
    status: str | None = None,
    form_template_id: int | None = None,
) -> list[dict[str, Any]]:
    stmt = select(FlowTemplate).order_by(FlowTemplate.id.desc())
    if status:
        stmt = stmt.where(FlowTemplate.status == status)
    if category:
        stmt = stmt.where(FlowTemplate.category == category)
    if form_template_id is not None:
        stmt = stmt.where(FlowTemplate.form_template_id == form_template_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(FlowTemplate.name.like(like) | FlowTemplate.code.like(like))
    return [_to_out(db, t) for t in db.scalars(stmt).all()]


def to_out(db: Session, template: FlowTemplate) -> dict[str, Any]:
    return _to_out(db, template)


def _assert_code_available(db: Session, code: str | None, *, exclude_id: int | None = None) -> None:
    if not code:
        return
    stmt = select(FlowTemplate.id).where(FlowTemplate.code == code)
    if exclude_id is not None:
        stmt = stmt.where(FlowTemplate.id != exclude_id)
    if db.scalar(stmt):
        raise ConflictError(f"流程编码 {code} 已存在", code="FLOW_CODE_EXISTS")


def _assert_form_template(db: Session, form_template_id: int) -> FormTemplate:
    form_template = form_service.get_or_404(db, form_template_id)
    if form_template.status == FormStatus.DISABLED:
        raise UnprocessableError(
            f"表单模板「{form_template.name}」已停用，不能绑定到流程",
            code="FORM_TEMPLATE_DISABLED",
        )
    return form_template


def create_template(
    db: Session,
    *,
    name: str,
    form_template_id: int,
    code: str | None,
    category: str | None,
    description: str | None,
    initiator_scope: dict[str, Any] | None,
    actor: User,
    ip: str | None = None,
) -> FlowTemplate:
    _assert_code_available(db, code)
    _assert_form_template(db, form_template_id)

    template = FlowTemplate(
        name=name,
        code=code,
        form_template_id=form_template_id,
        category=category,
        description=description,
        initiator_scope=initiator_scope or {"type": "all"},
        status=FlowStatus.DRAFT,
        created_by=actor.id,
    )
    db.add(template)
    db.flush()

    version = FlowVersion(
        template_id=template.id,
        version_no=1,
        definition=default_definition(),
        # 草稿版本先指向表单的当前版本（或最新草稿），发布时再正式锁定
        locked_form_version_id=_resolve_form_version_id(db, form_template_id),
        status=FlowVersionStatus.DRAFT,
        created_by=actor.id,
    )
    db.add(version)
    db.flush()

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FLOW_TEMPLATE,
        biz_id=template.id,
        action=AuditAction.CREATE,
        summary=f"新建流程模板「{template.name}」",
        detail={"name": template.name, "form_template_id": form_template_id},
        ip=ip,
    )
    db.commit()
    db.refresh(template)
    return template


def _resolve_form_version_id(db: Session, form_template_id: int) -> int:
    """绑定用的表单版本：优先已发布的，没有则用最新草稿（供设计期预览）。"""
    template = form_service.get_or_404(db, form_template_id)
    published = form_service._current_version(db, template)
    if published is not None:
        return published.id
    versions = form_service._versions_of(db, form_template_id)
    if not versions:
        raise UnprocessableError(
            "该表单还没有任何版本，无法绑定", code="FORM_VERSION_MISSING"
        )
    return versions[0].id


def update_template(
    db: Session,
    template: FlowTemplate,
    *,
    name: str | None = None,
    category: str | None = None,
    description: str | None = None,
    initiator_scope: dict[str, Any] | None = None,
    actor: User,
    ip: str | None = None,
) -> FlowTemplate:
    if name is not None:
        template.name = name
    if category is not None:
        template.category = category
    if description is not None:
        template.description = description
    if initiator_scope is not None:
        template.initiator_scope = initiator_scope

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FLOW_TEMPLATE,
        biz_id=template.id,
        action=AuditAction.UPDATE,
        summary=f"修改流程模板「{template.name}」",
        ip=ip,
    )
    db.commit()
    db.refresh(template)
    return template


def set_template_status(
    db: Session, template: FlowTemplate, status: str, *, actor: User, ip: str | None = None
) -> FlowTemplate:
    if status == FlowStatus.PUBLISHED:
        raise UnprocessableError(
            "启用状态由发布版本自动决定，不能手工设置", code="STATUS_MANAGED_BY_PUBLISH"
        )
    template.status = status
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FLOW_TEMPLATE,
        biz_id=template.id,
        action=AuditAction.DISABLE if status == FlowStatus.DISABLED else AuditAction.ENABLE,
        summary=f"{'停用' if status == FlowStatus.DISABLED else '草稿化'}流程模板「{template.name}」",
        ip=ip,
    )
    db.commit()
    db.refresh(template)
    return template


def delete_template(
    db: Session, template: FlowTemplate, *, actor: User, ip: str | None = None
) -> None:
    """删除流程模板（连同全部版本）。

    **有实例引用时拒绝删除**：`flow_instances.flow_version_id` 指向版本，
    硬删会撞外键（用户看到 500）。语义上也该拒绝 ——
    已经跑过的单据不能因为模板被删就失去追溯依据。要停用改用「停用」。
    """
    instance_count = db.scalar(
        select(func.count(FlowInstance.id)).where(
            FlowInstance.flow_template_id == template.id
        )
    ) or 0
    if instance_count:
        raise ConflictError(
            f"该流程已有 {instance_count} 个流程实例，不能删除。"
            "如需停止使用，请改为「停用」；实例会保留以支持追溯。",
            code="FLOW_HAS_INSTANCES",
            extra={"instance_count": instance_count},
        )

    biz_id, name = template.id, template.name
    db.delete(template)
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FLOW_TEMPLATE,
        biz_id=biz_id,
        action=AuditAction.DELETE,
        summary=f"删除流程模板「{name}」",
        ip=ip,
    )
    db.commit()


# --------------------------------------------------------------------------- 版本


def get_version_or_404(db: Session, version_id: int) -> FlowVersion:
    version = db.get(FlowVersion, version_id)
    if version is None:
        raise NotFoundError("流程版本不存在", code="FLOW_VERSION_NOT_FOUND")
    return version


def list_versions(db: Session, template: FlowTemplate) -> list[FlowVersion]:
    return _versions_of(db, template.id)


def version_to_out(db: Session, version: FlowVersion) -> dict[str, Any]:
    form_version = db.get(FormVersion, version.locked_form_version_id)
    return {
        "id": version.id,
        "template_id": version.template_id,
        "version_no": version.version_no,
        "status": version.status,
        "remark": version.remark,
        "definition": version.definition,
        "locked_form_version_id": version.locked_form_version_id,
        "locked_form_version_no": form_version.version_no if form_version else None,
        "validation_report": version.validation_report,
        "created_by": version.created_by,
        "published_at": version.published_at,
        "created_at": version.created_at,
    }


def create_version(
    db: Session, template: FlowTemplate, *, from_version_id: int | None, actor: User, ip: str | None = None
) -> FlowVersion:
    """新建 DRAFT 版本。已存在 DRAFT 时直接复用它（幂等）。"""
    existing = db.scalar(
        select(FlowVersion).where(
            FlowVersion.template_id == template.id,
            FlowVersion.status == FlowVersionStatus.DRAFT,
        )
    )
    if existing is not None:
        return existing

    # 草稿始终跟随表单的最新发布版本；发布时会再次确认并锁定它。
    locked = _resolve_form_version_id(db, template.form_template_id)
    if from_version_id is not None:
        base = get_version_or_404(db, from_version_id)
        if base.template_id != template.id:
            raise NotFoundError("该版本不属于此流程模板", code="FLOW_VERSION_MISMATCH")
        definition = base.definition
    else:
        current = _current_version(db, template)
        if current is not None:
            definition = current.definition
        else:
            versions = _versions_of(db, template.id)
            definition = versions[0].definition if versions else default_definition()

    next_no = (
        db.scalar(
            select(func.max(FlowVersion.version_no)).where(FlowVersion.template_id == template.id)
        )
        or 0
    ) + 1

    version = FlowVersion(
        template_id=template.id,
        version_no=next_no,
        definition=definition,
        locked_form_version_id=locked,
        status=FlowVersionStatus.DRAFT,
        created_by=actor.id,
    )
    db.add(version)
    db.flush()

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FLOW_TEMPLATE,
        biz_id=template.id,
        action=AuditAction.CREATE,
        summary=f"「{template.name}」新建草稿版本 v{next_no}",
        ip=ip,
    )
    db.commit()
    db.refresh(version)
    return version


def _current_version(db: Session, template: FlowTemplate) -> FlowVersion | None:
    if template.current_version_id is not None:
        version = db.get(FlowVersion, template.current_version_id)
        if version is not None and version.status == FlowVersionStatus.PUBLISHED:
            return version
    return db.scalar(
        select(FlowVersion)
        .where(
            FlowVersion.template_id == template.id,
            FlowVersion.status == FlowVersionStatus.PUBLISHED,
        )
        .order_by(FlowVersion.version_no.desc())
        .limit(1)
    )


def update_version(
    db: Session,
    version: FlowVersion,
    *,
    definition: dict[str, Any],
    locked_form_version_id: int | None = None,
    remark: str | None = None,
    actor: User,
    ip: str | None = None,
) -> FlowVersion:
    """保存草稿版本。

    同表单：**不做语义校验**，设计器要能存下没配完的流程
    （刚加的审批节点还没选审批人）。语义问题留到发布时拦。
    """
    if version.status != FlowVersionStatus.DRAFT:
        raise UnprocessableError(
            f"v{version.version_no} 已发布，不能再修改；请新建版本",
            code="VERSION_NOT_EDITABLE",
        )

    # 形状校验：pydantic 会拒绝不认识的节点类型等，这类数据存进去渲染不了
    parsed = FlowDefinition.model_validate(definition)

    version.definition = parsed.model_dump(mode="json")
    if locked_form_version_id is not None:
        version.locked_form_version_id = locked_form_version_id
    if remark is not None:
        version.remark = remark

    db.commit()
    db.refresh(version)
    return version


def validate_version(db: Session, version: FlowVersion) -> list[ValidationIssue]:
    """F2.7 校验：结构 + 业务规则，并绑定表单 schema 做引用完整性检查。"""
    try:
        definition = FlowDefinition.model_validate(version.definition)
    except Exception as exc:  # noqa: BLE001
        return [
            ValidationIssue(
                code="DEFINITION_MALFORMED",
                message=f"流程定义无法解析：{exc}",
                severity="error",
            )
        ]

    form_schema = None
    form_version = db.get(FormVersion, version.locked_form_version_id)
    if form_version is not None:
        try:
            form_schema = parse_form_schema(form_version.schema)
        except Exception:  # noqa: BLE001 - 表单坏了不该让流程校验崩掉
            form_schema = None

    return validate_flow_definition(definition, form_schema)


def publish_version(
    db: Session,
    version: FlowVersion,
    *,
    remark: str | None,
    actor: User,
    ip: str | None = None,
) -> FlowVersion:
    """发布（F2.6）：校验通过后冻结，并**锁定表单版本**。"""
    if version.status == FlowVersionStatus.PUBLISHED:
        raise ConflictError(f"v{version.version_no} 已经是发布状态", code="ALREADY_PUBLISHED")
    if version.status == FlowVersionStatus.ARCHIVED:
        raise UnprocessableError(
            f"v{version.version_no} 已归档，不能重新发布", code="VERSION_ARCHIVED"
        )

    template = db.get(FlowTemplate, version.template_id)
    if template is None:
        raise NotFoundError("流程模板不存在", code="FLOW_TEMPLATE_NOT_FOUND")

    # ★ 先确定要锁定的表单版本，再按它校验：
    # 草稿可能创建于表单改版之前；如果先按旧版本校验、发布时再锁新版本，
    # 会放过「引用已被删除字段」的流程，运行期条件/权限就会静默失配。
    form_template = form_service.get_or_404(db, template.form_template_id)
    published_form = form_service._current_version(db, form_template)
    if published_form is None:
        raise UnprocessableError(
            f"表单模板「{form_template.name}」还没有发布版本，请先发布表单",
            code="FORM_NOT_PUBLISHED",
        )
    version.locked_form_version_id = published_form.id

    issues = validate_version(db, version)
    version.validation_report = {
        "valid": not has_errors(issues),
        "issues": [i.to_dict() for i in issues],
        "at": utcnow().isoformat(),
    }
    if has_errors(issues):
        db.commit()
        raise UnprocessableError(
            "流程校验未通过，无法发布",
            code="FLOW_INVALID",
            extra={"errors": [i.to_dict() for i in issues if i.severity == "error"]},
        )

    for previous in db.scalars(
        select(FlowVersion).where(
            FlowVersion.template_id == version.template_id,
            FlowVersion.status == FlowVersionStatus.PUBLISHED,
        )
    ).all():
        previous.status = FlowVersionStatus.ARCHIVED

    version.status = FlowVersionStatus.PUBLISHED
    version.published_at = utcnow()
    if remark:
        version.remark = remark

    template.current_version_id = version.id
    if template.status == FlowStatus.DRAFT:
        template.status = FlowStatus.PUBLISHED

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FLOW_TEMPLATE,
        biz_id=version.template_id,
        action=AuditAction.PUBLISH,
        summary=f"发布流程版本 v{version.version_no}（锁定表单 v{published_form.version_no}）",
        detail={
            "version_id": version.id,
            "locked_form_version_id": published_form.id,
        },
        ip=ip,
    )
    db.commit()
    db.refresh(version)
    return version


def delete_version(
    db: Session, version: FlowVersion, *, actor: User, ip: str | None = None
) -> None:
    if version.status != FlowVersionStatus.DRAFT:
        raise UnprocessableError("只有草稿版本可以删除", code="VERSION_NOT_DELETABLE")
    template_id, version_no = version.template_id, version.version_no
    db.delete(version)
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.FLOW_TEMPLATE,
        biz_id=template_id,
        action=AuditAction.DELETE,
        summary=f"删除流程草稿版本 v{version_no}",
        ip=ip,
    )
    db.commit()


# --------------------------------------------------------------------------- 发起范围


def is_initiator_allowed(
    db: Session, template: FlowTemplate, user: User
) -> bool:
    """判断用户是否在发起范围内（F2.5）。

    范围是 `{"type": "all"}` / `{"type": "role", "role_ids": [...]}` /
    `{"type": "dept", "dept_ids": [...]}`（部门含子部门）。
    """
    scope = template.initiator_scope or {"type": "all"}
    scope_type = scope.get("type", "all")

    if scope_type == "all":
        return True
    if scope_type == "role":
        role_ids = set(scope.get("role_ids") or [])
        return bool(role_ids & {link.role_id for link in user.role_links})
    if scope_type == "dept":
        dept_ids = set(scope.get("dept_ids") or [])
        if not dept_ids or user.dept_id is None:
            return False
        # 用物化路径判断：用户所在部门是授权部门或其子孙部门即可发起
        user_dept = db.get(Department, user.dept_id)
        if user_dept is None:
            return False
        for dept_id in dept_ids:
            dept = db.get(Department, dept_id)
            if dept is not None and user_dept.path.startswith(dept.path):
                return True
        return False
    return False
