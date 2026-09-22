"""组织管理 DTO（F6.1 用户 / F6.2 部门 / F6.3 角色）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.constants import DeptStatus, RoleStatus, UserStatus

USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"


# --------------------------------------------------------------------------- 角色


class RoleBrief(BaseModel):
    id: int
    code: str
    name: str


class RoleOut(RoleBrief):
    description: str | None = None
    is_builtin: bool = False
    status: str = RoleStatus.ACTIVE
    member_count: int = 0
    created_at: datetime | None = None


class RoleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    status: RoleStatus = RoleStatus.ACTIVE


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    status: RoleStatus | None = None


# --------------------------------------------------------------------------- 部门


class DeptBrief(BaseModel):
    id: int
    name: str
    code: str


class DeptOut(DeptBrief):
    parent_id: int | None = None
    path: str = "/"
    level: int = 1
    manager_user_id: int | None = None
    manager_name: str | None = None
    sort_order: int = 0
    status: str = DeptStatus.ACTIVE
    #: 直属成员数（不含子部门）
    member_count: int = 0
    children: list[DeptOut] = Field(default_factory=list)


class DeptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    parent_id: int | None = None
    manager_user_id: int | None = None
    sort_order: int = 0
    status: DeptStatus = DeptStatus.ACTIVE


class DeptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    parent_id: int | None = None
    manager_user_id: int | None = None
    sort_order: int | None = None
    status: DeptStatus | None = None


class DeptMemberOut(BaseModel):
    id: int
    username: str
    real_name: str
    position: str | None = None
    status: str


# --------------------------------------------------------------------------- 用户


class UserOut(BaseModel):
    id: int
    username: str
    real_name: str
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None
    dept_id: int | None = None
    dept_name: str | None = None
    position: str | None = None
    status: str = UserStatus.ACTIVE
    is_superuser: bool = False
    roles: list[RoleBrief] = Field(default_factory=list)
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=6, max_length=72)
    real_name: str = Field(min_length=1, max_length=64)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    dept_id: int | None = None
    position: str | None = Field(default=None, max_length=64)
    status: UserStatus = UserStatus.ACTIVE
    role_ids: list[int] = Field(default_factory=list)


class UserUpdate(BaseModel):
    real_name: str | None = Field(default=None, min_length=1, max_length=64)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    dept_id: int | None = None
    position: str | None = Field(default=None, max_length=64)
    status: UserStatus | None = None
    role_ids: list[int] | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6, max_length=72)


class UserStatusRequest(BaseModel):
    status: UserStatus


class UserOption(BaseModel):
    """人员选择器返回的精简项（F3.2 表单的人员控件、审批人指定都会用到）。"""

    id: int
    username: str
    real_name: str
    dept_id: int | None = None
    dept_name: str | None = None
