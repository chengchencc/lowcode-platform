"""首启初始化（F6.5）：内置角色 + 示例部门 + 管理员账号 + 示例流程库。

幂等：已存在的一律跳过，所以可以放心地在每次启动时调用。

各段的开关（`backend/.env` / 环境变量）：
| 开关 | 默认 | 内容 |
|---|---|---|
| `SEED_DEMO_ORG` | 开 | 示例部门树与管理员账号 |
| `SEED_DEMO_ACCOUNTS` | **关** | 张三/李四/王五/赵六 四个试用账号（密码公开，线上必须关） |
| `SEED_SAMPLE_FLOWS` | 开 | 请假 / 报销 两套可直接发起的示例流程 |
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import BUILTIN_ROLES, RoleCode, UserStatus
from app.core.security import hash_password
from app.models import Department, Role, User, UserRole
from app.seeds import demo_accounts, sample_flows

logger = logging.getLogger(__name__)

#: 示例部门树：(名称, 编码, 父编码)
DEMO_DEPTS: tuple[tuple[str, str, str | None], ...] = (
    ("总公司", "HQ", None),
    ("技术部", "TECH", "HQ"),
    ("产品部", "PRODUCT", "HQ"),
    ("财务部", "FINANCE", "HQ"),
    ("人力资源部", "HR", "HQ"),
)


def _ensure_roles(db: Session) -> dict[str, Role]:
    existing = {r.code: r for r in db.scalars(select(Role)).all()}
    for code, name, description in BUILTIN_ROLES:
        if code not in existing:
            role = Role(code=code, name=name, description=description, is_builtin=True)
            db.add(role)
            db.flush()
            existing[code] = role
            logger.info("初始化内置角色：%s(%s)", name, code)
    return existing


def _ensure_depts(db: Session) -> dict[str, Department]:
    existing = {d.code: d for d in db.scalars(select(Department)).all()}
    for name, code, parent_code in DEMO_DEPTS:
        if code in existing:
            continue
        parent = existing.get(parent_code) if parent_code else None
        dept = Department(
            name=name,
            code=code,
            parent_id=parent.id if parent else None,
            level=(parent.level + 1) if parent else 1,
        )
        db.add(dept)
        db.flush()
        # 物化路径要等自增 id 出来后才能拼
        dept.path = f"{parent.path if parent else '/'}{dept.id}/"
        existing[code] = dept
        logger.info("初始化示例部门：%s", name)
    return existing


def _ensure_admin(
    db: Session, cfg: Settings, roles: dict[str, Role], depts: dict[str, Department]
) -> User | None:
    existing = db.scalar(select(User).where(User.username == cfg.admin_username))
    if existing is not None:
        return existing

    admin = User(
        username=cfg.admin_username,
        password_hash=hash_password(cfg.admin_password),
        real_name=cfg.admin_real_name,
        email=cfg.admin_email.lower() if cfg.admin_email else None,
        dept_id=depts["HQ"].id if "HQ" in depts else None,
        position="系统管理员",
        status=UserStatus.ACTIVE,
        is_superuser=True,
    )
    db.add(admin)
    db.flush()

    platform_admin = roles.get(RoleCode.PLATFORM_ADMIN)
    if platform_admin is not None:
        db.add(UserRole(user_id=admin.id, role_id=platform_admin.id))

    logger.warning(
        "已创建初始管理员：%s / %s —— 请登录后立即修改密码",
        cfg.admin_username,
        cfg.admin_password,
    )
    return admin


def run_seed(db: Session, cfg: Settings) -> None:
    roles = _ensure_roles(db)
    depts: dict[str, Department] = {}
    if cfg.seed_demo_org:
        depts = _ensure_depts(db)
    admin = _ensure_admin(db, cfg, roles, depts)
    db.commit()

    if cfg.seed_demo_accounts:
        demo_accounts.run_seed(db)
        db.commit()

    # 示例流程库要挂在某个 created_by 上，用管理员最自然
    if cfg.seed_sample_flows and admin is not None:
        sample_flows.run_seed(db, admin, role_ids={code: r.id for code, r in roles.items()})
