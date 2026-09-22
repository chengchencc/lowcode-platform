"""`ApproverProvider` 的数据库实现（PRD §3.3.2）。

引擎通过这个接口取数据，因此解析逻辑本身可以脱离数据库测试。
「部门主管」的解析链按 PRD §3.3.2 的落地方式：

    departments.manager_user_id
      → 部门内持有 dept_manager 角色的用户（兜底）
      → 逐级向上找有主管的祖先部门
      → 都没有 → 空（由引擎转管理员并标记异常）
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import RoleCode, UserStatus
from app.models import Department, Role, User, UserRole


class DbApproverProvider:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- 基础查询 ----

    def users_by_ids(self, user_ids: Sequence[int]) -> list[int]:
        ids = {int(i) for i in user_ids}
        if not ids:
            return []
        return list(
            self.db.scalars(
                select(User.id)
                .where(User.id.in_(ids), User.status == UserStatus.ACTIVE)
                .order_by(User.id)
            ).all()
        )

    def users_by_role(self, role_ids: Sequence[int]) -> list[int]:
        ids = {int(i) for i in role_ids}
        if not ids:
            return []
        rows = self.db.execute(
            select(UserRole.user_id)
            .join(User, User.id == UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                UserRole.role_id.in_(ids),
                User.status == UserStatus.ACTIVE,
                Role.status == "ACTIVE",
            )
            .distinct()
            .order_by(UserRole.user_id)
        ).all()
        return [r[0] for r in rows]

    def active_user_ids(self, user_ids: Sequence[int]) -> list[int]:
        return self.users_by_ids(user_ids)

    def admin_user_ids(self) -> list[int]:
        """平台管理员：超管 或 持有 platform_admin 角色。"""
        admins = set(
            self.db.scalars(
                select(User.id).where(
                    User.is_superuser.is_(True), User.status == UserStatus.ACTIVE
                )
            ).all()
        )
        role = self.db.scalar(select(Role).where(Role.code == RoleCode.PLATFORM_ADMIN))
        if role is not None:
            admins.update(self.users_by_role([role.id]))
        return sorted(admins)

    def current_active_users(self) -> list[int]:
        return list(
            self.db.scalars(
                select(User.id).where(User.status == UserStatus.ACTIVE).order_by(User.id)
            ).all()
        )

    # ---- 部门主管 ----

    def dept_manager(self, dept_id: int) -> list[int]:
        """部门主管。沿部门树向上找，直到找到有主管的部门。"""
        dept = self.db.get(Department, dept_id)
        if dept is None:
            return []

        # 自己 → 祖先（path 是物化路径，直接能算出祖先链）
        for candidate in self._self_and_ancestors(dept):
            if candidate.manager_user_id:
                found = self.users_by_ids([candidate.manager_user_id])
                if found:
                    return found
            by_role = self._dept_manager_by_role(candidate.id)
            if by_role:
                return by_role
        return []

    def _self_and_ancestors(self, dept: Department) -> list[Department]:
        ids = [int(p) for p in dept.path.split("/") if p]
        if not ids:
            return [dept]
        rows = {
            d.id: d
            for d in self.db.scalars(select(Department).where(Department.id.in_(ids))).all()
        }
        # path 是从根到自身的顺序，这里要**从自己往上**找
        ordered = [rows[i] for i in reversed(ids) if i in rows]
        return ordered or [dept]

    def _dept_manager_by_role(self, dept_id: int) -> list[int]:
        """兜底：该部门内持有「部门主管」内置角色的用户。"""
        role = self.db.scalar(select(Role).where(Role.code == RoleCode.DEPT_MANAGER))
        if role is None:
            return []
        rows = self.db.execute(
            select(UserRole.user_id)
            .join(User, User.id == UserRole.user_id)
            .where(
                UserRole.role_id == role.id,
                User.dept_id == dept_id,
                User.status == UserStatus.ACTIVE,
            )
            .distinct()
            .order_by(UserRole.user_id)
        ).all()
        return [r[0] for r in rows]
