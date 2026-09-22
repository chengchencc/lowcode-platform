"""认证（F6.4）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.constants import TokenType, UserStatus
from app.core.errors import BadRequestError, UnauthorizedError
from app.core.policy import is_admin, is_designer
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import Department, User
from app.schemas.auth import LoginResponse, MeResponse, RefreshResponse, UserBrief
from app.schemas.org import RoleBrief


def _to_brief(db: Session, user: User) -> UserBrief:
    dept_name: str | None = None
    if user.dept_id is not None:
        dept_name = db.scalar(select(Department.name).where(Department.id == user.dept_id))
    return UserBrief(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        email=user.email,
        phone=user.phone,
        avatar=user.avatar,
        position=user.position,
        dept_id=user.dept_id,
        dept_name=dept_name,
        is_superuser=user.is_superuser,
        status=user.status,
        roles=[
            RoleBrief(id=link.role.id, code=link.role.code, name=link.role.name)
            for link in user.role_links
            if link.role is not None
        ],
        last_login_at=user.last_login_at,
    )


def _issue(user: User) -> dict:
    access, expires_at = create_token(
        user_id=user.id, token_version=user.token_version, token_type=TokenType.ACCESS
    )
    refresh, _ = create_token(
        user_id=user.id, token_version=user.token_version, token_type=TokenType.REFRESH
    )
    return {"access_token": access, "refresh_token": refresh, "expires_at": expires_at}


def login(
    db: Session, *, username: str, password: str, ip: str | None = None
) -> LoginResponse:
    user = db.scalar(select(User).where(User.username == username))

    # 用户不存在与密码错误返回同一个错误码，避免账号枚举
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("用户名或密码错误", code="INVALID_CREDENTIALS")
    if user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("账号已停用，请联系管理员", code="ACCOUNT_DISABLED")

    user.last_login_at = utcnow()
    db.commit()
    db.refresh(user)

    tokens = _issue(user)
    return LoginResponse(**tokens, user=_to_brief(db, user))


def refresh(db: Session, *, refresh_token: str) -> RefreshResponse:
    payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
    user = db.get(User, payload.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("账号状态异常，请重新登录", code="ACCOUNT_DISABLED")
    if payload.token_version != user.token_version:
        raise UnauthorizedError("登录已失效，请重新登录", code="TOKEN_REVOKED")
    return RefreshResponse(**_issue(user))


def me(db: Session, user: User) -> MeResponse:
    return MeResponse(
        user=_to_brief(db, user),
        is_admin=is_admin(user),
        is_designer=is_designer(user),
    )


def change_password(
    db: Session, user: User, *, old_password: str, new_password: str
) -> None:
    if not verify_password(old_password, user.password_hash):
        raise BadRequestError("当前密码不正确", code="OLD_PASSWORD_MISMATCH")
    if old_password == new_password:
        raise BadRequestError("新密码不能与当前密码相同", code="PASSWORD_UNCHANGED")

    user.password_hash = hash_password(new_password)
    # 递增后，所有已签发的 token（含当前这一个）立即失效，前端需引导重新登录
    user.token_version += 1
    db.commit()


def logout(db: Session, user: User) -> None:
    """登出 = 递增 token_version，使该用户全部在线会话失效。"""
    user.token_version += 1
    db.commit()
