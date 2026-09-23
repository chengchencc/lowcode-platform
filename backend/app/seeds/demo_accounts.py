"""示例账号（PRD F6.5）。

空系统里只有一个 admin，试用的人没法把一条流程跑完 —— 审批人得先有人。
这里补齐四个角色上的人，并顺手把示例部门的主管挂上，让「部门主管」这条
最常见的审批人来源**开箱即用**。

**默认关闭**（`SEED_DEMO_ACCOUNTS=false`）：这批账号密码固定且公开，
线上环境打开等于给人留后门。容器化试用形态由 compose 显式打开，
README 里写明上线前要关掉。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import RoleCode, UserStatus
from app.core.security import hash_password
from app.models import Department, Role, User, UserRole

logger = logging.getLogger(__name__)

#: 示例账号的统一密码。公开的，只用于试用环境。
DEMO_PASSWORD = "demo123456"

#: (用户名, 姓名, 部门编码, 角色, 是否设为该部门主管)
DEMO_USERS: tuple[tuple[str, str, str, str | None, bool], ...] = (
    ("zhangsan", "张三", "TECH", None, False),
    ("lisi", "李四", "TECH", RoleCode.DEPT_MANAGER, True),
    ("wangwu", "王五", "FINANCE", RoleCode.FINANCE, True),
    ("zhaoliu", "赵六", "HQ", RoleCode.DESIGNER, True),
)


def run_seed(db: Session) -> None:
    roles = {r.code: r for r in db.scalars(select(Role)).all()}
    depts = {d.code: d for d in db.scalars(select(Department)).all()}
    created: list[str] = []

    for username, real_name, dept_code, role_code, is_manager in DEMO_USERS:
        dept = depts.get(dept_code)
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username,
                password_hash=hash_password(DEMO_PASSWORD),
                real_name=real_name,
                dept_id=dept.id if dept else None,
                status=UserStatus.ACTIVE,
            )
            db.add(user)
            db.flush()
            created.append(username)

        # 角色与部门主管都可能被人手工改过 —— 只在缺失时补，不覆盖
        role = roles.get(role_code) if role_code else None
        if role is not None:
            has_role = db.scalar(
                select(UserRole.id).where(
                    UserRole.user_id == user.id, UserRole.role_id == role.id
                )
            )
            if has_role is None:
                db.add(UserRole(user_id=user.id, role_id=role.id))

        if is_manager and dept is not None and dept.manager_user_id is None:
            dept.manager_user_id = user.id

    db.flush()
    if created:
        logger.warning(
            "已创建示例账号：%s（统一密码 %s）—— 仅供试用，上线前请关闭 SEED_DEMO_ACCOUNTS",
            "、".join(created),
            DEMO_PASSWORD,
        )
