"""任务接口：工作台四列表 + 统一动作入口（F4.1 / F4.3）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from app.core.deps import CurrentUser, DbSession
from app.core.pagination import Page, PageParams, build_page, paginate
from app.schemas.common import OkResp
from app.schemas.instance import AssignmentActRequest, InstanceOut, TaskRow, TodoSummary
from app.services import instance_service, task_service

router = APIRouter(prefix="/tasks", tags=["任务"])


# --------------------------------------------------------------------------- 四列表


@router.get("/todo", response_model=Page[TaskRow], summary="我的待办（F4.1）")
def list_todo(
    db: DbSession,
    user: CurrentUser,
    paging: Annotated[PageParams, Depends()],
    keyword: Annotated[str | None, Query(description="标题/编号")] = None,
    flow_template_id: Annotated[int | None, Query()] = None,
) -> dict:
    stmt = task_service.build_todo_query(
        db, user=user, keyword=keyword, flow_template_id=flow_template_id
    )
    rows, total = paginate(db, stmt, paging)
    # include_group：会签组要显示「同组还有 N 条」，前端据此提示
    return build_page(task_service.assignment_rows(db, rows, include_group=True), total, paging)


@router.get("/done", response_model=Page[TaskRow], summary="我的已办")
def list_done(
    db: DbSession,
    user: CurrentUser,
    paging: Annotated[PageParams, Depends()],
    keyword: Annotated[str | None, Query()] = None,
    flow_template_id: Annotated[int | None, Query()] = None,
) -> dict:
    stmt = task_service.build_done_query(
        db, user=user, keyword=keyword, flow_template_id=flow_template_id
    )
    rows, total = paginate(db, stmt, paging)
    return build_page(task_service.assignment_rows(db, rows), total, paging)


@router.get("/cc", response_model=Page[TaskRow], summary="抄送给我")
def list_cc(
    db: DbSession,
    user: CurrentUser,
    paging: Annotated[PageParams, Depends()],
    unread_only: Annotated[bool, Query()] = False,
    keyword: Annotated[str | None, Query()] = None,
) -> dict:
    stmt = task_service.build_cc_query(db, user=user, unread_only=unread_only, keyword=keyword)
    rows, total = paginate(db, stmt, paging)
    return build_page(task_service.assignment_rows(db, rows), total, paging)


@router.get("/mine", response_model=Page[InstanceOut], summary="我发起的")
def list_mine(
    db: DbSession,
    user: CurrentUser,
    paging: Annotated[PageParams, Depends()],
    instance_status: Annotated[str | None, Query(alias="status")] = None,
    keyword: Annotated[str | None, Query()] = None,
) -> dict:
    stmt = task_service.build_mine_query(
        db, user=user, status=instance_status, keyword=keyword
    )
    rows, total = paginate(db, stmt, paging)
    return build_page(
        [instance_service.to_out(db, r, viewer=user) for r in rows], total, paging
    )


@router.get("/summary", response_model=TodoSummary, summary="角标计数")
def summary(db: DbSession, user: CurrentUser) -> dict:
    return task_service.todo_summary(db, user)


# --------------------------------------------------------------------------- 单个任务


@router.get("/assignments/{assignment_id}", summary="任务详情")
def get_assignment(assignment_id: int, db: DbSession, user: CurrentUser) -> dict:
    from app.core.errors import ForbiddenError

    assignment = task_service.get_assignment_or_404(db, assignment_id)
    if assignment.user_id != user.id:
        from app.core.policy import is_admin

        if not is_admin(user):
            raise ForbiddenError("这不是分配给你的任务", code="NOT_ASSIGNEE")
    return task_service.assignment_rows(db, [assignment], include_group=True)[0]


@router.get("/assignments/{assignment_id}/return-targets", summary="可退回的节点")
def return_targets(assignment_id: int, db: DbSession, user: CurrentUser) -> list[dict]:
    from app.core.errors import ForbiddenError

    assignment = task_service.get_assignment_or_404(db, assignment_id)
    if assignment.user_id != user.id:
        raise ForbiddenError("这不是分配给你的任务", code="NOT_ASSIGNEE")
    return task_service.return_targets_for(db, assignment)


@router.post(
    "/assignments/{assignment_id}/act", response_model=InstanceOut, summary="★ 处理任务（F4.3）"
)
def act(
    assignment_id: int,
    payload: AssignmentActRequest,
    db: DbSession,
    user: CurrentUser,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> dict:
    """同意 / 驳回 / 退回 / 提交。

    - 网络重放：`X-Request-Id` 落到唯一索引，重复请求返回同一结果
    - 并发冲突：`expected_version` 与实例当前版本不符时返回 409
    """
    task_service.act(
        db,
        assignment_id=assignment_id,
        actor=user,
        action=payload.action,
        opinion=payload.opinion,
        attachment_ids=payload.attachment_ids,
        field_patch=payload.field_patch,
        return_target=payload.return_target,
        expected_version=payload.expected_version,
        request_id=x_request_id,
    )
    assignment = task_service.get_assignment_or_404(db, assignment_id)
    instance = instance_service.get_or_404(db, assignment.instance_id)
    db.refresh(instance)
    return instance_service.to_out(db, instance, viewer=user)


@router.post("/assignments/{assignment_id}/read", response_model=OkResp, summary="抄送已读")
def mark_read(assignment_id: int, db: DbSession, user: CurrentUser) -> OkResp:
    task_service.mark_read(db, assignment_id=assignment_id, actor=user)
    return OkResp(message="已标记为已读")
