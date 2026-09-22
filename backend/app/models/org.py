"""组织模型：部门 / 用户 / 角色 / 用户-角色关联（PRD §6 前四张表）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DeptStatus, RoleStatus, UserStatus
from app.db.base import Base, CreatedAtMixin, IntType, PkMixin, TimestampMixin


class Department(Base, PkMixin, TimestampMixin):
    """部门，树形结构。

    用**物化路径** `path`（形如 `/1/4/9/`）表示层级：子树查询是一条
    `path LIKE '/1/4/%'` 而不是递归 CTE —— 两种数据库上都简单且够快。
    这也是 PRD §3.3.2「部门主管」审批人解析和后续数据权限的基础。
    """

    __tablename__ = "departments"

    parent_id: Mapped[int | None] = mapped_column(
        IntType, ForeignKey("departments.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    path: Mapped[str] = mapped_column(String(512), nullable=False, default="/", index=True)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    # 部门主管：PRD §3.3.2「部门主管」审批人来源的解析依据。
    # 刻意不建外键 —— departments.manager_user_id 与 users.dept_id 互相引用会成环，
    # 而 SQLite 上加环外键需要批处理重建表。完整性由 service 层保证。
    manager_user_id: Mapped[int | None] = mapped_column(IntType, nullable=True, index=True)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DeptStatus.ACTIVE)

    parent: Mapped[Department | None] = relationship(
        "Department", remote_side="Department.id", back_populates="children"
    )
    children: Mapped[list[Department]] = relationship(
        "Department",
        back_populates="parent",
        order_by="Department.sort_order, Department.id",
        foreign_keys="Department.parent_id",
    )
    users: Mapped[list[User]] = relationship(
        "User", back_populates="department", foreign_keys="User.dept_id"
    )

    @property
    def manager(self) -> User | None:
        """主管用户对象。需要调用方已加载 `users` 或单独按 id 查询。"""
        if self.manager_user_id is None:
            return None
        return next((u for u in self.users if u.id == self.manager_user_id), None)


class User(Base, PkMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    real_name: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)

    dept_id: Mapped[int | None] = mapped_column(
        IntType, ForeignKey("departments.id"), nullable=True, index=True
    )
    position: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=UserStatus.ACTIVE, index=True
    )
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: 改密 / 强制下线时 +1，使已签发的 JWT 立即失效（F6.4）
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    department: Mapped[Department | None] = relationship(
        "Department", back_populates="users", foreign_keys="User.dept_id"
    )
    role_links: Mapped[list[UserRole]] = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ---- 便捷访问 ----

    @property
    def role_codes(self) -> list[str]:
        """当前用户拥有的角色 code 列表（无需额外查询：role_links 预加载、role 是 joined）。"""
        return [link.role.code for link in self.role_links if link.role is not None]

    def has_role(self, *codes: str) -> bool:
        return bool(set(self.role_codes) & set(codes))

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE


class Role(Base, PkMixin, TimestampMixin):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: 内置角色（platform_admin / designer / dept_manager / finance）不可删除、code 不可改
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RoleStatus.ACTIVE)

    user_links: Mapped[list[UserRole]] = relationship(
        "UserRole", back_populates="role", cascade="all, delete-orphan"
    )


class UserRole(Base, PkMixin, CreatedAtMixin):
    """用户-角色关联。用显式关联对象而非裸 secondary 表，便于记录授权人与时间。"""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uk_user_role"),)

    user_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_by: Mapped[int | None] = mapped_column(IntType, nullable=True)

    user: Mapped[User] = relationship("User", back_populates="role_links")
    # joined：取 user.role_codes 时不产生 N+1
    role: Mapped[Role] = relationship("Role", back_populates="user_links", lazy="joined")
