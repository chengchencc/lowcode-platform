"""实例接口：发起、草稿、详情、历史、撤回/终止（F3.x / F4.2 / F4.6）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import ClientIp, CurrentUser, DbSession
from app.core.pagination import Page, PageParams, build_page, paginate
from app.schemas.common import OkResp
from app.schemas.instance import (
    DraftCreate,
    DraftUpdate,
    InstanceOut,
    StartOptionsOut,
    SubmitRequest,
    TerminateRequest,
    WithdrawRequest,
)
from app.services import instance_service, render_service, snapshot_service

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
    from app.services import timeline_service

    instance = instance_service.get_or_404(db, instance_id)
    instance_service.assert_can_view(db, instance, user)
    return timeline_service.list_actions(db, instance)


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
    return {**snapshot_service.to_out(db, snapshot), "data": snapshot.data}


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
    return snapshot_service.compare(db, from_id, to_id)


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
) -> dict:
    stmt = instance_service.build_query(
        db,
        user=user,
        scope=scope,
        status=instance_status,
        flow_template_id=flow_template_id,
        keyword=keyword,
    )
    rows, total = paginate(db, stmt, paging)
    return build_page(
        [instance_service.to_out(db, r, viewer=user) for r in rows], total, paging
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
