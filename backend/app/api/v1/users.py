"""用户管理接口（F6.1）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.core.deps import AdminUser, ClientIp, CurrentUser, DbSession
from app.core.errors import BadRequestError
from app.core.pagination import Page, PageParams, build_page, paginate
from app.schemas.common import OkResp
from app.schemas.org import (
    ResetPasswordRequest,
    UserCreate,
    UserOption,
    UserOut,
    UserStatusRequest,
    UserUpdate,
)
from app.services import user_service

router = APIRouter(prefix="/users", tags=["用户管理"])

MAX_IMPORT_BYTES = 5 * 1024 * 1024


@router.get("", response_model=Page[UserOut], summary="用户列表")
def list_users(
    db: DbSession,
    _: AdminUser,
    paging: Annotated[PageParams, Depends()],
    keyword: Annotated[str | None, Query(description="用户名/姓名/邮箱/手机号模糊匹配")] = None,
    dept_id: Annotated[int | None, Query(description="部门筛选")] = None,
    include_sub_depts: Annotated[bool, Query(description="含子部门")] = False,
    user_status: Annotated[str | None, Query(alias="status", description="ACTIVE/DISABLED")] = None,
) -> dict:
    stmt = user_service.build_query(
        db,
        keyword=keyword,
        dept_id=dept_id,
        status=user_status,
        include_sub_depts=include_sub_depts,
    )
    rows, total = paginate(db, stmt, paging)
    return build_page(user_service.to_out_many(db, rows), total, paging)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="新建用户")
def create_user(
    payload: UserCreate, db: DbSession, actor: AdminUser, ip: ClientIp
) -> UserOut:
    user = user_service.create(db, payload, actor=actor, ip=ip)
    return user_service.to_out_many(db, [user])[0]


@router.get("/options", response_model=list[UserOption], summary="人员选择器候选项")
def user_options(
    db: DbSession,
    _: CurrentUser,
    keyword: Annotated[str | None, Query()] = None,
    dept_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[UserOption]:
    """登录用户即可调用 —— 发起表单的人员控件、审批人指定都需要它。"""
    return user_service.search_options(db, keyword=keyword, dept_id=dept_id, limit=limit)


@router.post("/import", summary="CSV 批量导入")
def import_users(
    db: DbSession,
    actor: AdminUser,
    ip: ClientIp,
    file: Annotated[UploadFile, File(description="UTF-8 编码的 CSV")],
) -> dict:
    content = file.file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise BadRequestError("文件超过 5MB 上限", code="FILE_TOO_LARGE")
    return user_service.import_csv(db, content, actor=actor, ip=ip)


@router.get("/{user_id}", response_model=UserOut, summary="用户详情")
def get_user(user_id: int, db: DbSession, _: AdminUser) -> UserOut:
    return user_service.to_out_many(db, [user_service.get_or_404(db, user_id)])[0]


@router.put("/{user_id}", response_model=UserOut, summary="修改用户")
def update_user(
    user_id: int, payload: UserUpdate, db: DbSession, actor: AdminUser, ip: ClientIp
) -> UserOut:
    user = user_service.update(db, user_service.get_or_404(db, user_id), payload, actor=actor, ip=ip)
    return user_service.to_out_many(db, [user])[0]


@router.delete("/{user_id}", response_model=OkResp, summary="删除用户")
def delete_user(user_id: int, db: DbSession, actor: AdminUser, ip: ClientIp) -> OkResp:
    user_service.delete(db, user_service.get_or_404(db, user_id), actor=actor, ip=ip)
    return OkResp(message="用户已删除")


@router.post("/{user_id}/reset-password", response_model=OkResp, summary="重置密码")
def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    db: DbSession,
    actor: AdminUser,
    ip: ClientIp,
) -> OkResp:
    user_service.reset_password(
        db, user_service.get_or_404(db, user_id), payload.new_password, actor=actor, ip=ip
    )
    return OkResp(message="密码已重置，该用户需重新登录")


@router.post("/{user_id}/status", response_model=UserOut, summary="启用 / 停用")
def set_status(
    user_id: int,
    payload: UserStatusRequest,
    db: DbSession,
    actor: AdminUser,
    ip: ClientIp,
) -> UserOut:
    user = user_service.set_status(
        db, user_service.get_or_404(db, user_id), payload.status, actor=actor, ip=ip
    )
    return user_service.to_out_many(db, [user])[0]
