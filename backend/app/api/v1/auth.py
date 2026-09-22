"""认证接口。"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import ClientIp, CurrentUser, DbSession
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RefreshRequest,
    RefreshResponse,
)
from app.schemas.common import OkResp
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse, summary="登录")
def login(payload: LoginRequest, db: DbSession, ip: ClientIp) -> LoginResponse:
    return auth_service.login(db, username=payload.username, password=payload.password, ip=ip)


@router.post("/refresh", response_model=RefreshResponse, summary="刷新 access token")
def refresh(payload: RefreshRequest, db: DbSession) -> RefreshResponse:
    return auth_service.refresh(db, refresh_token=payload.refresh_token)


@router.post("/logout", response_model=OkResp, summary="登出（使全部会话失效）")
def logout(db: DbSession, user: CurrentUser) -> OkResp:
    auth_service.logout(db, user)
    return OkResp(message="已登出")


@router.get("/me", response_model=MeResponse, summary="当前登录用户")
def me(db: DbSession, user: CurrentUser) -> MeResponse:
    return auth_service.me(db, user)


@router.post("/change-password", response_model=OkResp, summary="修改密码")
def change_password(
    payload: ChangePasswordRequest, db: DbSession, user: CurrentUser
) -> OkResp:
    auth_service.change_password(
        db, user, old_password=payload.old_password, new_password=payload.new_password
    )
    # 改密会递增 token_version，当前 token 已失效，前端需跳回登录页
    return OkResp(message="密码已修改，请重新登录")
