"""实例接口：发起、草稿、详情、历史、归档导出、撤回/终止（F3.x / F4.x / F8）。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import ClientIp, CurrentUser, DbSession
from app.core.errors import ForbiddenError, UnprocessableError
from app.core.pagination import Page, PageParams, build_page, paginate
from app.core.policy import is_admin
from app.engine.ext_fields import ExtFieldSpec
from app.schemas.common import OkResp
from app.schemas.instance import (
    DraftCreate,
    DraftUpdate,
    ExtFieldCreate,
    InstanceOut,
    StartOptionsOut,
    SubmitRequest,
    TerminateRequest,
    WithdrawRequest,
)
from app.services import (
    export_service,
    instance_service,
    render_service,
    search_service,
    snapshot_service,
)

router = APIRouter(prefix="/instances", tags=["流程实例"])


# --------------------------------------------------------------------------- 发起中心


@router.get("/available-flows", response_model=list[dict], summary="可发起的流程（F3.1）")
def available_flows(db: DbSession, user: CurrentUser) -> list[dict]:
    return instance_service.list_available_flows(db, user)


@router.get(
    "/start-options/{flow_template_id}", response_model=StartOptionsOut, summary="发起页元数据（F3.2）"
)
def start_options(flow_template_id: int, db: DbSession, user: CurrentUser) -> dict:
    from app.services import flow_service

    template = flow_service.get_or_404(db, flow_template_id)
    return instance_service.start_options(db, template, user)


# --------------------------------------------------------------------------- 草稿


@router.post(
    "/drafts",
    response_model=InstanceOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建草稿（F3.3）",
)
def create_draft(
    payload: DraftCreate, db: DbSession, user: CurrentUser, ip: ClientIp
) -> dict:
    from app.services import flow_service

    template = flow_service.get_or_404(db, payload.flow_template_id)
    instance = instance_service.create_draft(
        db, template=template, actor=user, data=payload.data, title=payload.title
    )
    return instance_service.to_out(db, instance, viewer=user)


@router.get("/drafts", response_model=list[InstanceOut], summary="我的草稿箱")
def list_drafts(db: DbSession, user: CurrentUser) -> list[dict]:
    return [
        instance_service.to_out(db, i, viewer=user)
        for i in instance_service.list_drafts(db, user)
    ]


@router.put("/{instance_id}/draft", response_model=InstanceOut, summary="暂存草稿")
def update_draft(
    instance_id: int, payload: DraftUpdate, db: DbSession, user: CurrentUser
) -> dict:
    instance = instance_service.update_draft(
        db,
        instance_service.get_or_404(db, instance_id),
        actor=user,
        data=payload.data,
        title=payload.title,
    )
    return instance_service.to_out(db, instance, viewer=user)


@router.delete("/{instance_id}", response_model=OkResp, summary="删除草稿")
def delete_draft(instance_id: int, db: DbSession, user: CurrentUser) -> OkResp:
    instance_service.delete_draft(
        db, instance_service.get_or_404(db, instance_id), actor=user
    )
    return OkResp(message="草稿已删除")


# --------------------------------------------------------------------------- 提交


@router.post("/{instance_id}/submit", response_model=InstanceOut, summary="提交（F3.4）")
def submit(
    instance_id: int, payload: SubmitRequest, db: DbSession, user: CurrentUser
) -> dict:
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.submit(
        db,
        instance,
        actor=user,
        data=payload.data,
        note=payload.note,
        attachment_ids=payload.attachment_ids,
        assignee_picks=payload.assignee_picks,
    )
    return instance_service.to_out(db, instance, viewer=user)


@router.post(
    "/{instance_id}/resubmit", response_model=InstanceOut, summary="驳回后重新提交（F3.6）"
)
def resubmit(
    instance_id: int, payload: SubmitRequest, db: DbSession, user: CurrentUser
) -> dict:
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.submit(
        db,
        instance,
        actor=user,
        data=payload.data,
        note=payload.note,
        attachment_ids=payload.attachment_ids,
        assignee_picks=payload.assignee_picks,
        resubmit=True,
    )
    return instance_service.to_out(db, instance, viewer=user)


# --------------------------------------------------------------------------- 详情


@router.get("/{instance_id}/render", summary="★ 详情页一次取全（F4.2）")
def render(
    instance_id: int,
    db: DbSession,
    user: CurrentUser,
    assignment_id: Annotated[int | None, Query(description="以哪个待办的身份查看")] = None,
    snapshot_id: Annotated[int | None, Query(description="查看历史时点（F4.6）")] = None,
) -> dict:
    return render_service.render_instance(
        db,
        instance_service.get_or_404(db, instance_id),
        viewer=user,
        assignment_id=assignment_id,
        snapshot_id=snapshot_id,
    )


@router.get("/{instance_id}/progress", summary="进度条")
def progress(instance_id: int, db: DbSession, user: CurrentUser) -> list[dict]:
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.assert_can_view(db, instance, user)
    from app.engine.compile import compile_definition

    compiled = compile_definition(instance_service.version_of(db, instance).definition)
    return render_service.build_progress(db, instance, compiled)


@router.get("/{instance_id}/timeline", summary="处理历史时间线（F4.6）")
def timeline(instance_id: int, db: DbSession, user: CurrentUser) -> list[dict]:
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.assert_can_view(db, instance, user)
    # 复用 render 的查看者视角：时间线里的字段 diff 也按 D-04 裁剪。
    return render_service.render_instance(db, instance, viewer=user).get("actions", [])


# ⚠️ 顺序要紧：`/snapshots/diff` 必须排在 `/snapshots/{snapshot_id}` **之前**。
# FastAPI 按声明顺序匹配，否则 "diff" 会被当成 snapshot_id 解析 →
# 422「Input should be a valid integer, unable to parse string as an integer」。
@router.get("/{instance_id}/snapshots/diff", summary="两个快照的字段对照")
def snapshot_diff(
    instance_id: int,
    db: DbSession,
    user: CurrentUser,
    from_id: Annotated[int, Query(alias="from")],
    to_id: Annotated[int, Query(alias="to")],
) -> list[dict]:
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.assert_can_view(db, instance, user)
    rows = snapshot_service.compare(db, from_id, to_id)
    # D-04：运行中查看历史对照时，hidden 字段的 key/旧值/新值都不下发。
    rendered = render_service.render_instance(
        db, instance, viewer=user, snapshot_id=to_id
    )
    # render 的 permissions 已裁剪为仅可见字段；不在其中即 hidden。
    permissions = rendered.get("permissions", {})
    return [
        row
        for row in rows
        if permissions.get(row.get("key"), {}).get("visible", False)
    ]


@router.get("/{instance_id}/snapshots/{snapshot_id}", summary="历史时点快照")
def get_snapshot(
    instance_id: int, snapshot_id: int, db: DbSession, user: CurrentUser
) -> dict:
    from app.core.errors import NotFoundError

    instance = instance_service.get_or_404(db, instance_id)
    instance_service.assert_can_view(db, instance, user)
    snapshot = db.get(snapshot_service.DataSnapshot, snapshot_id)
    if snapshot is None or snapshot.instance_id != instance.id:
        raise NotFoundError("快照不存在", code="SNAPSHOT_NOT_FOUND")
    # D-04：快照页与详情页共用查看者视角；运行中 hidden 字段的 key/值不下发。
    rendered = render_service.render_instance(
        db, instance, viewer=user, snapshot_id=snapshot_id
    )
    data = {
        **snapshot.data,
        "values": rendered.get("values", {}),
        "ext_fields": rendered.get("ext_fields", []),
    }
    return {**snapshot_service.to_out(db, snapshot), "data": data}


# --------------------------------------------------------------------------- 检索


@router.get("", response_model=Page[InstanceOut], summary="实例列表")
def list_instances(
    db: DbSession,
    user: CurrentUser,
    paging: Annotated[PageParams, Depends()],
    scope: Annotated[str, Query(pattern="^(mine|related|all)$")] = "mine",
    instance_status: Annotated[str | None, Query(alias="status")] = None,
    flow_template_id: Annotated[int | None, Query()] = None,
    keyword: Annotated[str | None, Query(description="标题/编号模糊匹配")] = None,
    filters: Annotated[str | None, Query(description="业务字段筛选 JSON（M13）")] = None,
) -> dict:
    stmt = instance_service.build_query(
        db,
        user=user,
        scope=scope,
        status=instance_status,
        flow_template_id=flow_template_id,
        keyword=keyword,
    )
    if filters:
        if flow_template_id is None:
            raise UnprocessableError(
                "按业务字段筛选时必须指定流程模板", code="FLOW_TEMPLATE_REQUIRED"
            )
        if scope != "mine" and not is_admin(user):
            raise UnprocessableError(
                "当前列表不支持业务字段筛选", code="FILTER_SCOPE_NOT_SUPPORTED"
            )
        configs = search_service.allowed_fields(
            db, flow_template_id, start_only=not is_admin(user)
        )
        stmt = search_service.apply_filters(
            stmt, search_service.parse_filters(filters, configs)
        )
    rows, total = paginate(db, stmt, paging)
    return build_page(
        [instance_service.to_out(db, r, viewer=user) for r in rows], total, paging
    )


@router.get("/search-fields", summary="可筛选字段元数据（M13）")
def search_fields(
    db: DbSession,
    user: CurrentUser,
    flow_template_id: Annotated[int, Query()],
    scope: Annotated[str, Query(pattern="^(mine|archive)$")] = "mine",
) -> list[dict]:
    if scope == "archive" and not is_admin(user):
        raise ForbiddenError("只有平台管理员可以筛选归档", code="ADMIN_REQUIRED")
    configs = search_service.allowed_fields(
        db, flow_template_id, start_only=scope == "mine" and not is_admin(user)
    )
    return [
        {
            "field_key": config.field_key,
            "label": config.label,
            "filter_kind": config.filter_kind,
            "options": config.options or [],
            "start_visible": config.start_visible,
        }
        for config in configs.values()
    ]


@router.get("/my-flow-templates", summary="我发起过的流程（普通用户可选）")
def my_flow_templates(db: DbSession, user: CurrentUser) -> list[dict]:
    return instance_service.list_available_flows(db, user)


# --------------------------------------------------------------------------- 归档检索与导出（F8）


@router.get("/archive", response_model=Page[InstanceOut], summary="归档列表（F8.1）")
def list_archive(
    db: DbSession,
    user: CurrentUser,
    paging: Annotated[PageParams, Depends()],
    instance_status: Annotated[
        str | None, Query(alias="status", description="归档仅支持 APPROVED")
    ] = None,
    flow_template_id: Annotated[int | None, Query()] = None,
    initiator_id: Annotated[int | None, Query()] = None,
    keyword: Annotated[str | None, Query(description="标题/编号模糊匹配")] = None,
    finished_from: Annotated[datetime | None, Query(description="完成时间起（含）")] = None,
    finished_to: Annotated[datetime | None, Query(description="完成时间止（含）")] = None,
    filters: Annotated[str | None, Query(description="业务字段筛选 JSON（M13）")] = None,
) -> dict:
    """已归档实例的检索（PRD F8.1）。

    管理员专属：这张表是**全组织的单据**，不是「与我相关的」。
    普通用户的入口是工作台里的「我发起的 / 抄送给我」。
    """
    if not is_admin(user):
        raise ForbiddenError("只有平台管理员可以检索全部归档", code="ADMIN_REQUIRED")

    stmt = instance_service.build_archive_query(
        db,
        statuses=_status_list(instance_status),
        flow_template_id=flow_template_id,
        initiator_id=initiator_id,
        keyword=keyword,
        finished_from=finished_from,
        finished_to=finished_to,
    )
    if filters:
        if flow_template_id is None:
            raise UnprocessableError(
                "按业务字段筛选时必须指定流程模板", code="FLOW_TEMPLATE_REQUIRED"
            )
        configs = search_service.allowed_fields(db, flow_template_id, start_only=False)
        stmt = search_service.apply_filters(stmt, search_service.parse_filters(filters, configs))
    rows, total = paginate(db, stmt, paging)
    return build_page(
        [instance_service.to_out(db, r, viewer=user) for r in rows], total, paging
    )


@router.get("/archive/export", summary="导出归档 CSV（F8.2）")
def export_archive(
    db: DbSession,
    user: CurrentUser,
    instance_status: Annotated[str | None, Query(alias="status")] = None,
    flow_template_id: Annotated[int | None, Query()] = None,
    initiator_id: Annotated[int | None, Query()] = None,
    keyword: Annotated[str | None, Query()] = None,
    finished_from: Annotated[datetime | None, Query()] = None,
    finished_to: Annotated[datetime | None, Query()] = None,
    filters: Annotated[str | None, Query(description="业务字段筛选 JSON（M13）")] = None,
) -> Response:
    """按同一组筛选条件导出 CSV（列 = 字段标签，含运行中追加的动态字段）。"""
    if not is_admin(user):
        raise ForbiddenError("只有平台管理员可以导出归档", code="ADMIN_REQUIRED")

    stmt = instance_service.build_archive_query(
        db,
        statuses=_status_list(instance_status),
        flow_template_id=flow_template_id,
        initiator_id=initiator_id,
        keyword=keyword,
        finished_from=finished_from,
        finished_to=finished_to,
    )
    if filters:
        if flow_template_id is None:
            raise UnprocessableError(
                "按业务字段筛选时必须指定流程模板", code="FLOW_TEMPLATE_REQUIRED"
            )
        configs = search_service.allowed_fields(db, flow_template_id, start_only=False)
        stmt = search_service.apply_filters(stmt, search_service.parse_filters(filters, configs))
    rows = list(db.scalars(stmt.limit(export_service.MAX_EXPORT_ROWS)).all())
    return _csv_response(export_service.build_csv(db, rows), export_service.csv_filename())


@router.get("/{instance_id}/export", summary="导出单个实例 CSV")
def export_instance(instance_id: int, db: DbSession, user: CurrentUser) -> Response:
    """发起人/处理人/管理员都能导出**自己看得见**的单据。

    导出等于把整张单据的数据一次性拿走，可见性校验不能省 ——
    它和详情页用的是同一条规则（PRD §2）。单实例导出复用 render 的
    查看者视角：运行中只导出可见字段，终态导出归档全量（D-04）。
    """
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.assert_can_view(db, instance, user)
    rendered = render_service.render_instance(db, instance, viewer=user)
    return _csv_response(
        export_service.build_csv_from_render(rendered),
        export_service.csv_filename(f"flowform-{instance.code or instance.id}"),
    )


def _status_list(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    values = [v.strip().upper() for v in raw.split(",") if v.strip()]
    invalid = [value for value in values if value != "APPROVED"]
    if invalid:
        raise UnprocessableError(
            "归档列表只支持 APPROVED",
            code="ARCHIVE_STATUS_INVALID",
            extra={"invalid": invalid},
        )
    return values or None


def _csv_response(text: str, filename: str) -> Response:
    # 文件名可能含中文，用 RFC 5987 的 filename* 交给浏览器解码
    quoted = quote(filename)
    return Response(
        content=text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"archive.csv\"; filename*=UTF-8''{quoted}",
        },
    )


# --------------------------------------------------------------------------- 撤回 / 撤销 / 终止


@router.post("/{instance_id}/withdraw", response_model=InstanceOut, summary="撤回（§3.5.4）")
def withdraw(
    instance_id: int, payload: WithdrawRequest, db: DbSession, user: CurrentUser
) -> dict:
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.withdraw(db, instance, actor=user, reason=payload.reason)
    db.refresh(instance)
    return instance_service.to_out(db, instance, viewer=user)


@router.post("/{instance_id}/abandon", response_model=InstanceOut, summary="撤销（放弃申请）")
def abandon(instance_id: int, db: DbSession, user: CurrentUser) -> dict:
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.abandon(db, instance, actor=user)
    db.refresh(instance)
    return instance_service.to_out(db, instance, viewer=user)


@router.post("/{instance_id}/terminate", response_model=InstanceOut, summary="终止（管理员）")
def terminate(
    instance_id: int, payload: TerminateRequest, db: DbSession, user: CurrentUser
) -> dict:
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.terminate(db, instance, actor=user, reason=payload.reason)
    db.refresh(instance)
    return instance_service.to_out(db, instance, viewer=user)


# --------------------------------------------------------------------------- 机制 C：运行中追加字段


@router.post("/{instance_id}/ext-fields", summary="运行中追加字段（F5.1，管理员/设计者）")
def add_ext_field(
    instance_id: int, payload: ExtFieldCreate, db: DbSession, user: CurrentUser
) -> dict:
    """追加成功后**直接返回详情页数据** —— 前端一次请求就能刷新表单与权限。"""
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.add_ext_field(
        db,
        instance,
        actor=user,
        spec=ExtFieldSpec(
            label=payload.label,
            type=payload.type,
            editable_node_ids=tuple(payload.editable_node_ids),
            required=payload.required,
            section_key=payload.section_key,
            config=payload.config,
            placeholder=payload.placeholder,
        ),
    )
    return render_service.render_instance(db, instance, viewer=user)


@router.post(
    "/{instance_id}/ext-fields/{field_key}/disable", summary="停用动态字段（不可物理删除）"
)
def disable_ext_field(
    instance_id: int, field_key: str, db: DbSession, user: CurrentUser
) -> dict:
    instance = instance_service.get_or_404(db, instance_id)
    instance_service.disable_ext_field(db, instance, actor=user, field_key=field_key)
    return render_service.render_instance(db, instance, viewer=user)
