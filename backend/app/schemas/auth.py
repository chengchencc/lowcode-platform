"""认证相关 DTO（F6.4）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.org import RoleBrief

#: 与 core/security.BCRYPT_MAX_BYTES 对齐：超过 72 字节的密码会被 bcrypt 静默截断，
#: 宁可在这里直接拒绝，也不要让用户以为设了一个更长的密码。
PASSWORD_MAX = 72


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class UserBrief(BaseModel):
    """当前登录用户信息。前端 auth store 与顶栏使用。"""

    id: int
    username: str
    real_name: str
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None
    position: str | None = None
    dept_id: int | None = None
    dept_name: str | None = None
    is_superuser: bool = False
    status: str
    roles: list[RoleBrief] = Field(default_factory=list)
    last_login_at: datetime | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    #: access token 过期的 unix 秒，前端据此提前刷新
    expires_at: int
    user: UserBrief


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: int


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=PASSWORD_MAX)
    #: 最短 6 位：与用户创建保持一致。「新密码不能与旧密码相同」由 service 层判定，
    #: 因为那里才有 hash 可校验，纯 schema 层比较明文属于重复逻辑。
    new_password: str = Field(min_length=6, max_length=PASSWORD_MAX)


class MeResponse(BaseModel):
    user: UserBrief
    is_admin: bool
    is_designer: bool
