"""流程实例服务（F3.x / F4.x）。

职责边界：**引擎语义在 `engine/service.py`**，这里只做
草稿、可见性、查询装配与「把引擎结果翻译成接口 DTO」。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    AssignmentStatus,
    FlowStatus,
    InstanceStatus,
)
from app.core.errors import ForbiddenError, NotFoundError, UnprocessableError
from app.core.idgen import auto_number_values, create_with_code
from app.core.policy import is_admin, is_designer
from app.engine.auto_fill import auto_fill_values, default_values
from app.engine.compile import compile_definition
from app.engine.ext_fields import ExtFieldSpec
from app.engine.form_rules import apply_form_rules
from app.engine.permissions import (
    FieldPermission,
    resolve_field_permissions,
)
from app.engine.service import EngineService
from app.engine.types import NODE_TYPE_LABELS
from app.models import (
    FlowInstance,
    FlowTemplate,
    FlowVersion,
    FormVersion,
    TaskAssignment,
    User,
)
from app.schemas.form_schema import FormSchema, parse_form_schema
from app.services import file_service, flow_service, form_service, view_filter
from app.services.approver_provider import DbApproverProvider


def engine_for(db: Session) -> EngineService:
    """构造引擎。放在这里而不是让调用方自己拼，是为了保证 provider 一致。"""
    return EngineService(db, provider=DbApproverProvider(db))


# --------------------------------------------------------------------------- 发起中心


def list_available_flows(db: Session, user: User) -> list[dict[str, Any]]:
    """可发起的流程（F3.1）。按 initiator_scope 过滤，非授权用户看不到入口。"""
    templates = list(
        db.scalars(
            select(FlowTemplate)
            .where(FlowTemplate.status == FlowStatus.PUBLISHED)
            .order_by(FlowTemplate.id.desc())
        ).all()
    )
    out: list[dict[str, Any]] = []
    for template in templates:
        if not flow_service.is_initiator_allowed(db, template, user):
            continue
        out.append(flow_service.to_out(db, template))
    return out


# --------------------------------------------------------------------------- 发起页


def start_options(db: Session, template: FlowTemplate, user: User) -> dict[str, Any]:
    """发起页所需的全部元数据（F3.2 / F3.5）。

    一次给全：表单 schema、**发起节点的字段权限**、需要发起人指定审批人的节点。
    前端据此渲染，不必自己推导权限。
    """
    if template.status != FlowStatus.PUBLISHED:
        raise UnprocessableError("该流程尚未发布", code="FLOW_NOT_PUBLISHED")
    if not flow_service.is_initiator_allowed(db, template, user):
        raise ForbiddenError("你不在该流程的发起范围内", code="NOT_IN_SCOPE")

    current = _current_version(db, template)
    if current is None:
        raise NotFoundError("流程没有已发布版本", code="FLOW_VERSION_MISSING")

    form_version = db.get(FormVersion, current.locked_form_version_id)
    if form_version is None:
        raise NotFoundError("锁定的表单版本不存在", code="FORM_VERSION_MISSING")
    form_schema = parse_form_schema(form_version.schema)

    # 表单模板可能已经发布了更新的版本；流程没重新发布时，发起页仍用旧版 schema。
    # 把最新发布版本号告诉前端，用来提示「字段/可见性改动尚未生效」。
    form_template = form_service.get_or_404(db, template.form_template_id)
    latest_form_version = form_service._current_version(db, form_template)

    compiled = compile_definition(current.definition)
    base_permissions = resolve_field_permissions(
        form_schema=form_schema,
        node_type="start",
        rule=compiled.definition.start.fields_permission,
        values={},
    )
    # 发起时自动填充的字段由系统带入，发起阶段强制只读（值仍可被后续节点按权限使用）
    filled = auto_fill_values(form_schema, user_id=user.id, dept_id=user.dept_id)
    auto_number_keys = {
        field.key
        for section in form_schema.sections
        for field in section.fields
        if field.auto_number is not None
    }
    for key in [*filled, *auto_number_keys]:
        permission = base_permissions.get(key)
        if permission is not None:
            base_permissions[key] = FieldPermission(
                visible=permission.visible,
                editable=False,
                required=False,
                reason=f"{permission.reason} → 系统编号/自动填充(只读)",
            )
    # 默认值只带入、不锁定：发起人仍可改
    defaults = default_values(form_schema, user_id=user.id, dept_id=user.dept_id)
    permissions = apply_form_rules(base_permissions, form_schema, {})
    permission_map = {k: v.to_dict() for k, v in permissions.items()}
    base_map = {k: v.to_dict() for k, v in base_permissions.items()}
    form_rules = [
        rule.model_dump(mode="json") for rule in getattr(form_schema, "rules", []) or []
    ]

    # D-04：运行中只下发可见字段的 schema/权限/值；终态归档由调用方另行处理。
    return {
        "flow_template_id": template.id,
        "flow_template_name": template.name,
        "flow_version_id": current.id,
        "flow_version_no": current.version_no,
        "form_version_id": form_version.id,
        "form_version_no": form_version.version_no,
        # 表单模板最新已发布版本；大于 form_version_no 时说明流程需要重新发布
        "form_latest_version_no": (
            latest_form_version.version_no if latest_form_version else None
        ),
        "schema_data": view_filter.filter_schema(form_version.schema, permission_map),
        "permissions": view_filter.filter_permissions(permission_map),
        "base_permissions": view_filter.filter_permissions(base_map),
        "form_rules": view_filter.filter_rules(form_rules, permission_map),
        # 发起时的系统自动填充值：前端据此预填表单
        "auto_fill_values": view_filter.filter_values(filled, permission_map),
        # 可修改的默认值（发起人仍可改）
        "default_values": view_filter.filter_values(defaults, permission_map),
        # 需要发起人指定审批人的节点（F3.5）
        "initiator_select_nodes": _initiator_select_nodes(db, compiled, current),
        "nodes": _progress_nodes(compiled),
    }


def _current_version(db: Session, template: FlowTemplate) -> FlowVersion | None:
    if template.current_version_id is not None:
        version = db.get(FlowVersion, template.current_version_id)
        if version is not None and version.status == "PUBLISHED":
            return version
    return db.scalar(
        select(FlowVersion)
        .where(FlowVersion.template_id == template.id, FlowVersion.status == "PUBLISHED")
        .order_by(FlowVersion.version_no.desc())
        .limit(1)
    )


def _initiator_select_nodes(db: Session, compiled, version: FlowVersion) -> list[dict[str, Any]]:
    """找出所有「发起人指定审批人」的节点，附带候选范围。"""
    out: list[dict[str, Any]] = []
    for node in compiled.nodes.values():
        rule = getattr(node.raw, "assignee", None)
        if rule is None or not any(s.type == "initiator_select" for s in rule.sources):
            continue
        scope = rule.initiator_select
        out.append(
            {
                "node_id": node.id,
                "node_name": node.name,
                "scope_role_ids": list(scope.scope_role_ids) if scope else [],
                "scope_dept_ids": list(scope.scope_dept_ids) if scope else [],
            }
        )
    return out


def _progress_nodes(compiled) -> list[dict[str, Any]]:
    """进度条的节点骨架（发起页可以先展示「会走哪几步」）。"""
    out: list[dict[str, Any]] = []
    for node_id in compiled.root_list:
        node = compiled.nodes[node_id]
        if node.type == "condition":
            out.append({
                "node_id": node.id, "name": node.name, "type": node.type,
                "type_label": NODE_TYPE_LABELS.get(node.type, node.type),
                "branches": [
                    {
                        "branch_id": branch.id,
                        "name": branch.name or branch.id,
                        "is_else": branch.when is None,
                        "nodes": [
                            {
                                "node_id": child,
                                "name": compiled.nodes[child].name,
                                "type": compiled.nodes[child].type,
                                "type_label": NODE_TYPE_LABELS.get(compiled.nodes[child].type, ""),
                            }
                            for child in compiled.branch_lists.get((node.id, branch.id), [])
                        ],
                    }
                    for branch in compiled.condition_branches.get(node.id, [])
                ],
            })
            continue
        out.append({
            "node_id": node.id,
            "name": node.name,
            "type": node.type,
            "type_label": NODE_TYPE_LABELS.get(node.type, node.type),
        })
    return out


# --------------------------------------------------------------------------- 草稿


def get_or_404(db: Session, instance_id: int) -> FlowInstance:
    instance = db.get(FlowInstance, instance_id)
    if instance is None:
        raise NotFoundError("流程实例不存在", code="INSTANCE_NOT_FOUND")
    return instance


def _title_from_form(form_schema: FormSchema | None, data: Mapping[str, Any] | None) -> str | None:
    """按表单配置的 `title_field` 取标题；没配置/没填则返回 None。"""
    key = getattr(form_schema, "title_field", None)
    if not key:
        return None
    value = (data or {}).get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()[:255]
    return None


def create_draft(
    db: Session,
    *,
    template: FlowTemplate,
    actor: User,
    data: Mapping[str, Any] | None = None,
    title: str | None = None,
) -> FlowInstance:
    """新建草稿（F3.3）。草稿**不生成审批任务**。"""
    if template.status != FlowStatus.PUBLISHED:
        raise UnprocessableError("该流程尚未发布", code="FLOW_NOT_PUBLISHED")
    if not flow_service.is_initiator_allowed(db, template, actor):
        raise ForbiddenError("你不在该流程的发起范围内", code="NOT_IN_SCOPE")

    current = _current_version(db, template)
    if current is None:
        raise NotFoundError("流程没有已发布版本", code="FLOW_VERSION_MISSING")

    dept_id = actor.dept_id
    form_version = db.get(FormVersion, current.locked_form_version_id)
    form_schema = parse_form_schema(form_version.schema) if form_version else None
    values = dict(data or {})
    if form_schema is not None:
        # 自动填充字段以服务端值为准；默认值只在空值时带入
        filled = auto_fill_values(form_schema, user_id=actor.id, dept_id=dept_id)
        # 草稿也只接受发起节点可编辑的字段：hidden/只读字段的客户端传值直接丢弃，
        # 避免它们从草稿一路带进提交（FORM-03）。
        permissions = resolve_field_permissions(
            form_schema=form_schema,
            node_type="start",
            rule=compile_definition(current.definition).definition.start.fields_permission,
            values={**values, **filled},
        )
        from app.engine.fields import apply_field_patch

        values, _ = apply_field_patch(
            current={},
            patch=values,
            permissions=permissions,
            form_schema=form_schema,
        )
        values.update(filled)
        for key, value in default_values(
            form_schema, user_id=actor.id, dept_id=dept_id
        ).items():
            if values.get(key) in (None, "", []):
                values[key] = value
        # 自动编号由服务端生成，忽略客户端传值
        values.update(auto_number_values(db, form_schema, existing={}))
    title_text = title or _title_from_form(form_schema, values) or template.name

    def factory(code: str) -> FlowInstance:
        return FlowInstance(
            code=code,
            flow_template_id=template.id,
            flow_version_id=current.id,
            form_version_id=current.locked_form_version_id,
            title=title_text[:255],
            initiator_id=actor.id,
            initiator_dept_id=dept_id,
            status=InstanceStatus.DRAFT,
            data_schema={},
            current_data=values,
        )

    instance = create_with_code(db, factory)
    db.commit()
    db.refresh(instance)
    return instance


def update_draft(
    db: Session,
    instance: FlowInstance,
    *,
    actor: User,
    data: Mapping[str, Any],
    title: str | None = None,
) -> FlowInstance:
    """暂存草稿。只接受发起节点可编辑的字段（与提交同一套权限）。"""
    _assert_initiator(instance, actor)
    if instance.status != InstanceStatus.DRAFT:
        raise UnprocessableError("只有草稿可以暂存", code="NOT_A_DRAFT")

    form_schema = form_schema_of(db, instance)
    compiled = compile_definition(version_of(db, instance).definition)
    # 自动填充字段由服务端写入：客户端传值直接丢弃
    filled = auto_fill_values(
        form_schema,
        user_id=actor.id,
        dept_id=instance.initiator_dept_id or actor.dept_id,
    )
    incoming = {key: value for key, value in data.items() if key not in filled}
    permissions = resolve_field_permissions(
        form_schema=form_schema,
        node_type="start",
        rule=compiled.definition.start.fields_permission,
        values={**data, **filled},
    )

    from app.engine.fields import apply_field_patch

    values, _diffs = apply_field_patch(
        current={**(instance.current_data or {}), **filled},
        patch=incoming,
        permissions=permissions,
        form_schema=form_schema,
    )
    # 可修改的默认值：只在字段仍为空时带入
    for key, value in default_values(
        form_schema,
        user_id=actor.id,
        dept_id=instance.initiator_dept_id or actor.dept_id,
    ).items():
        if values.get(key) in (None, "", []):
            values[key] = value
    # 自动编号：已有编号保持不变，缺失时补生成
    values.update(auto_number_values(db, form_schema, existing=instance.current_data or {}))
    instance.current_data = values
    derived = _title_from_form(form_schema, {**data, **filled})
    if title:
        instance.title = title[:255]
    elif derived:
        instance.title = derived
    elif form_schema.title_field:
        template = db.get(FlowTemplate, instance.flow_template_id)
        if template is not None:
            instance.title = template.name[:255]
    db.commit()
    db.refresh(instance)
    return instance


def list_drafts(db: Session, user: User) -> list[FlowInstance]:
    return list(
        db.scalars(
            select(FlowInstance)
            .where(
                FlowInstance.initiator_id == user.id,
                FlowInstance.status == InstanceStatus.DRAFT,
            )
            .order_by(FlowInstance.updated_at.desc())
        ).all()
    )


def delete_draft(db: Session, instance: FlowInstance, *, actor: User) -> None:
    _assert_initiator(instance, actor)
    if instance.status != InstanceStatus.DRAFT:
        raise UnprocessableError("只有草稿可以删除", code="NOT_A_DRAFT")
    db.delete(instance)
    db.commit()


def _assert_initiator(instance: FlowInstance, actor: User) -> None:
    if instance.initiator_id != actor.id:
        raise ForbiddenError("只有发起人可以修改", code="NOT_INITIATOR")


# --------------------------------------------------------------------------- 提交与动作（转发给引擎）


def submit(
    db: Session,
    instance: FlowInstance,
    *,
    actor: User,
    data: Mapping[str, Any],
    note: str | None = None,
    attachment_ids: Sequence[int] = (),
    assignee_picks: Mapping[str, Sequence[int]] | None = None,
    request_id: str | None = None,
    resubmit: bool = False,
):
    _assert_initiator(instance, actor)
    legacy_title = data.get("__title__")
    form_schema = form_schema_of(db, instance)
    derived = _title_from_form(form_schema, data)
    if isinstance(legacy_title, str) and legacy_title.strip():
        instance.title = legacy_title.strip()[:255]
    elif derived:
        instance.title = derived
    elif form_schema.title_field:
        template = db.get(FlowTemplate, instance.flow_template_id)
        if template is not None:
            instance.title = template.name[:255]

    # 提交前把表单里的临时附件（以及提交时携带的意见附件）绑定到实例，
    # 审批参与者才能下载。
    file_service.bind_instance_attachments(
        db,
        instance,
        form_schema,
        {**(instance.current_data or {}), **dict(data)},
        extra_ids=list(attachment_ids),
    )

    engine = engine_for(db)
    if resubmit:
        return engine.resubmit(
            instance=instance, actor=actor, data=data, note=note,
            attachment_ids=attachment_ids, assignee_picks=assignee_picks, request_id=request_id,
        )
    return engine.submit(
        instance=instance, actor=actor, data=data, note=note,
        attachment_ids=attachment_ids, assignee_picks=assignee_picks, request_id=request_id,
    )


def withdraw(db: Session, instance: FlowInstance, *, actor: User, reason: str | None, request_id=None):
    _assert_initiator(instance, actor)
    return engine_for(db).withdraw(instance=instance, actor=actor, reason=reason, request_id=request_id)


def abandon(db: Session, instance: FlowInstance, *, actor: User, request_id=None):
    _assert_initiator(instance, actor)
    return engine_for(db).abandon(instance=instance, actor=actor, request_id=request_id)


def terminate(db: Session, instance: FlowInstance, *, actor: User, reason: str, request_id=None):
    if not is_admin(actor):
        raise ForbiddenError("只有平台管理员可以终止流程", code="ADMIN_REQUIRED")
    return engine_for(db).terminate(instance=instance, actor=actor, reason=reason, request_id=request_id)


# --------------------------------------------------------------------------- 机制 C：运行中追加字段


def add_ext_field(
    db: Session,
    instance: FlowInstance,
    *,
    actor: User,
    spec: ExtFieldSpec,
    request_id: str | None = None,
):
    """给某个实例追加动态字段（PRD F5.1）。

    两道门槛缺一不可：
    1. **看得见这张单**（PRD §2 —— 设计者无审批数据管理权，不是相关人就看不了）
    2. **管理员或设计者**（F5.1：这是「改单据结构」的动作，不是业务动作）

    先校验再落库 —— 否则会出现「写成功但响应 403」这种前端没法处理的状态。
    """
    assert_can_view(db, instance, actor)
    if not is_designer(actor):
        raise ForbiddenError("只有平台管理员或设计者可以追加字段", code="DESIGNER_REQUIRED")
    return engine_for(db).add_ext_field(
        instance=instance, actor=actor, spec=spec, request_id=request_id
    )


def disable_ext_field(
    db: Session, instance: FlowInstance, *, actor: User, field_key: str, request_id: str | None = None
):
    assert_can_view(db, instance, actor)
    if not is_designer(actor):
        raise ForbiddenError("只有平台管理员或设计者可以停用字段", code="DESIGNER_REQUIRED")
    return engine_for(db).disable_ext_field(
        instance=instance, actor=actor, field_key=field_key, request_id=request_id
    )


# --------------------------------------------------------------------------- 可见性


def can_view(db: Session, instance: FlowInstance, user: User) -> bool:
    """PRD §2：发起人、历任/现任处理人、被抄送人、平台管理员可见。"""
    if is_admin(user):
        return True
    if instance.initiator_id == user.id:
        return True
    hit = db.scalar(
        select(TaskAssignment.id)
        .where(
            TaskAssignment.instance_id == instance.id,
            or_(
                TaskAssignment.user_id == user.id,
                # 转办/委托的原处理人仍保留查看权（PHASE3 M14 §4.4）
                TaskAssignment.origin_user_id == user.id,
            ),
        )
        .limit(1)
    )
    return hit is not None


def assert_can_view(db: Session, instance: FlowInstance, user: User) -> None:
    if not can_view(db, instance, user):
        raise ForbiddenError("你没有权限查看该单据", code="INSTANCE_FORBIDDEN")


# --------------------------------------------------------------------------- 表单/版本


def version_of(db: Session, instance: FlowInstance) -> FlowVersion:
    version = db.get(FlowVersion, instance.flow_version_id)
    if version is None:
        raise NotFoundError("流程版本不存在", code="FLOW_VERSION_MISSING")
    return version


def form_schema_of(db: Session, instance: FlowInstance) -> FormSchema:
    form_version = db.get(FormVersion, instance.form_version_id)
    if form_version is None:
        raise NotFoundError("表单版本不存在", code="FORM_VERSION_MISSING")
    return parse_form_schema(form_version.schema)


# --------------------------------------------------------------------------- 列表查询


def build_query(
    db: Session,
    *,
    user: User,
    scope: str = "mine",
    status: str | None = None,
    flow_template_id: int | None = None,
    keyword: str | None = None,
) -> Select:
    """`scope`：
    - `mine`   我发起的
    - `all`    全部（仅管理员）
    """
    stmt = select(FlowInstance)
    if scope == "mine":
        stmt = stmt.where(FlowInstance.initiator_id == user.id)
    elif not is_admin(user):
        # 非管理员请求 all 时退化成「与我相关的」（发起 + 参与 + 被抄送）
        sub = select(TaskAssignment.instance_id).where(
            or_(TaskAssignment.user_id == user.id, TaskAssignment.origin_user_id == user.id)
        )
        stmt = stmt.where(
            or_(FlowInstance.initiator_id == user.id, FlowInstance.id.in_(sub))
        )

    if status:
        stmt = stmt.where(FlowInstance.status == status)
    if flow_template_id is not None:
        stmt = stmt.where(FlowInstance.flow_template_id == flow_template_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(FlowInstance.title.like(like) | FlowInstance.code.like(like))
    return stmt.order_by(FlowInstance.id.desc())


def build_archive_query(
    db: Session,
    *,
    statuses: Sequence[str] | None = None,
    flow_template_id: int | None = None,
    keyword: str | None = None,
    initiator_id: int | None = None,
    finished_from: datetime | None = None,
    finished_to: datetime | None = None,
) -> Select:
    """归档检索（F8.1）。默认只看**已通过**；管理员查历史时可放开到其他终态。

    与 `build_query` 分开：那个是「我的/相关的单据」，语义是权限视角；
    这个不参权限 —— 调用方必须先确认调用者是管理员。
    """
    stmt = select(FlowInstance).where(
        FlowInstance.status.in_(list(statuses) if statuses else [InstanceStatus.APPROVED])
    )
    if flow_template_id is not None:
        stmt = stmt.where(FlowInstance.flow_template_id == flow_template_id)
    if initiator_id is not None:
        stmt = stmt.where(FlowInstance.initiator_id == initiator_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(FlowInstance.title.like(like) | FlowInstance.code.like(like))
    if finished_from is not None:
        stmt = stmt.where(FlowInstance.finished_at >= finished_from)
    if finished_to is not None:
        stmt = stmt.where(FlowInstance.finished_at <= finished_to)
    return stmt.order_by(FlowInstance.finished_at.desc(), FlowInstance.id.desc())


def to_out(db: Session, instance: FlowInstance, *, viewer: User | None = None) -> dict[str, Any]:
    """实例摘要。列表页与详情页头部共用。"""
    template = db.get(FlowTemplate, instance.flow_template_id)
    initiator = db.get(User, instance.initiator_id)
    from app.models import Department

    dept = db.get(Department, instance.initiator_dept_id) if instance.initiator_dept_id else None

    pending_assignments = db.scalar(
        select(func.count(TaskAssignment.id)).where(
            TaskAssignment.instance_id == instance.id,
            TaskAssignment.status == AssignmentStatus.PENDING,
        )
    ) or 0
    done_assignments = db.scalar(
        select(func.count(TaskAssignment.id)).where(
            TaskAssignment.instance_id == instance.id,
            TaskAssignment.status == AssignmentStatus.DONE,
        )
    ) or 0

    my_pending = 0
    if viewer is not None:
        my_pending = db.scalar(
            select(func.count(TaskAssignment.id)).where(
                TaskAssignment.instance_id == instance.id,
                TaskAssignment.user_id == viewer.id,
                TaskAssignment.status == AssignmentStatus.PENDING,
            )
        ) or 0

    return {
        "id": instance.id,
        "code": instance.code,
        "title": instance.title,
        "status": instance.status,
        "round": instance.round,
        "flow_template_id": instance.flow_template_id,
        "flow_template_name": template.name if template else None,
        "flow_version_id": instance.flow_version_id,
        "form_version_id": instance.form_version_id,
        "initiator_id": instance.initiator_id,
        "initiator_name": initiator.real_name if initiator else None,
        "initiator_dept_name": dept.name if dept else None,
        "current_node_keys": instance.current_node_keys or [],
        "abnormal": instance.abnormal,
        "pending_count": pending_assignments,
        "done_count": done_assignments,
        "my_pending_count": my_pending,
        "created_at": instance.created_at,
        "started_at": instance.started_at,
        "finished_at": instance.finished_at,
        "last_action_at": instance.last_action_at,
        "terminated_reason": instance.terminated_reason,
    }


def list_instances(db: Session, stmt: Select, params) -> tuple[list[FlowInstance], int]:
    from app.core.pagination import paginate

    return paginate(db, stmt, params)
