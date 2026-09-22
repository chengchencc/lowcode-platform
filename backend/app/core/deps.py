"""FastAPI 依赖：数据库会话、当前用户、角色门槛、客户端 IP。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.constants import TokenType, UserStatus
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.policy import is_admin, is_designer
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User

DbSession = Annotated[Session, Depends(get_db)]

# auto_error=False：缺 Authorization 头时返回 None，由我们自己抛出统一错误体，
# 而不是让 FastAPI 返回它默认的 {"detail": "Not authenticated"} 形状。
_bearer = HTTPBearer(auto_error=False, description="Bearer <access token>")


def get_client_ip(request: Request) -> str | None:
    # 经反向代理时以 X-Forwarded-For 的第一段为准
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


ClientIp = Annotated[str | None, Depends(get_client_ip)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("请先登录", code="NOT_AUTHENTICATED")

    payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    user = db.get(User, payload.user_id)
    if user is None:
        raise UnauthorizedError("用户不存在", code="USER_NOT_FOUND")
    if user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("账号已停用，请联系管理员", code="ACCOUNT_DISABLED")
    # 改密 / 强制下线 / 登出都会递增 token_version，使旧 token 立即失效（F6.4）
    if payload.token_version != user.token_version:
        raise UnauthorizedError("登录已失效，请重新登录", code="TOKEN_REVOKED")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if not is_admin(user):
        raise ForbiddenError("需要平台管理员权限", code="ADMIN_REQUIRED")
    return user


def require_designer(user: CurrentUser) -> User:
    if not is_designer(user):
        raise ForbiddenError("需要设计者权限", code="DESIGNER_REQUIRED")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
DesignerUser = Annotated[User, Depends(require_designer)]
