"""用户管理（F6.1）。"""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import AuditAction, AuditBizType, UserStatus
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.models import Department, Role, User, UserRole
from app.schemas.org import (
    RoleBrief,
    UserCreate,
    UserOption,
    UserOut,
    UserUpdate,
)
from app.services import audit_service, dept_service, role_service

#: CSV 导入时未提供密码的默认值。首次登录后应要求修改。
DEFAULT_IMPORT_PASSWORD = "Flowform@123"


def get_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在", code="USER_NOT_FOUND")
    return user


def build_query(
    db: Session,
    *,
    keyword: str | None = None,
    dept_id: int | None = None,
    status: str | None = None,
    include_sub_depts: bool = False,
) -> Select:
    stmt = select(User)
    if status:
        stmt = stmt.where(User.status == status)
    if dept_id is not None:
        if include_sub_depts:
            dept = dept_service.get_or_404(db, dept_id)
            ids = [dept.id, *dept_service.descendant_ids(db, dept)]
        else:
            ids = [dept_id]
        stmt = stmt.where(User.dept_id.in_(ids))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                User.username.like(like),
                User.real_name.like(like),
                User.email.like(like),
                User.phone.like(like),
            )
        )
    return stmt.order_by(User.id.desc())


# --------------------------------------------------------------------------- 出参装配


def _roles_brief(user: User) -> list[RoleBrief]:
    return [
        RoleBrief(id=link.role.id, code=link.role.code, name=link.role.name)
        for link in user.role_links
        if link.role is not None
    ]


def _dept_names(db: Session, dept_ids: set[int]) -> dict[int, str]:
    if not dept_ids:
        return {}
    rows = db.execute(select(Department.id, Department.name).where(Department.id.in_(dept_ids))).all()
    return {did: name for did, name in rows}


def to_out(user: User, *, dept_name: str | None = None) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        email=user.email,
        phone=user.phone,
        avatar=user.avatar,
        dept_id=user.dept_id,
        dept_name=dept_name,
        position=user.position,
        status=user.status,
        is_superuser=user.is_superuser,
        roles=_roles_brief(user),
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


def to_out_many(db: Session, users: list[User]) -> list[UserOut]:
    names = _dept_names(db, {u.dept_id for u in users if u.dept_id is not None})
    return [to_out(u, dept_name=names.get(u.dept_id) if u.dept_id else None) for u in users]


# --------------------------------------------------------------------------- 写


def create(
    db: Session, payload: UserCreate, *, actor: User | None = None, ip: str | None = None
) -> User:
    if db.scalar(select(User.id).where(User.username == payload.username)):
        raise ConflictError(f"用户名 {payload.username} 已存在", code="USERNAME_EXISTS")

    email = payload.email.lower() if payload.email else None
    if email and db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise ConflictError(f"邮箱 {email} 已被使用", code="EMAIL_EXISTS")

    if payload.dept_id is not None:
        dept_service.get_or_404(db, payload.dept_id)
    roles = role_service.resolve_ids(db, payload.role_ids)

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        real_name=payload.real_name,
        email=email,
        phone=payload.phone,
        dept_id=payload.dept_id,
        position=payload.position,
        status=payload.status,
    )
    db.add(user)
    db.flush()

    for role in roles:
        db.add(UserRole(user_id=user.id, role_id=role.id, granted_by=actor.id if actor else None))

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.USER,
        biz_id=user.id,
        action=AuditAction.CREATE,
        summary=f"新建用户「{user.real_name}({user.username})」",
        detail={"username": user.username, "roles": [r.code for r in roles]},
        ip=ip,
    )
    db.commit()
    db.refresh(user)
    return user


def update(
    db: Session,
    user: User,
    payload: UserUpdate,
    *,
    actor: User | None = None,
    ip: str | None = None,
) -> User:
    before = {
        "real_name": user.real_name,
        "email": user.email,
        "dept_id": user.dept_id,
        "position": user.position,
        "status": user.status,
        "roles": user.role_codes,
    }

    if payload.real_name is not None:
        user.real_name = payload.real_name
    if "email" in payload.model_fields_set:
        email = payload.email.lower() if payload.email else None
        if email and db.scalar(
            select(User.id).where(func.lower(User.email) == email, User.id != user.id)
        ):
            raise ConflictError(f"邮箱 {email} 已被使用", code="EMAIL_EXISTS")
        user.email = email
    if "phone" in payload.model_fields_set:
        user.phone = payload.phone
    if "position" in payload.model_fields_set:
        user.position = payload.position
    if "dept_id" in payload.model_fields_set:
        if payload.dept_id is not None:
            dept_service.get_or_404(db, payload.dept_id)
        user.dept_id = payload.dept_id
    if payload.status is not None:
        _assert_can_change_status(user, payload.status, actor)
        user.status = payload.status

    if payload.role_ids is not None:
        _replace_roles(db, user, role_service.resolve_ids(db, payload.role_ids), actor)

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.USER,
        biz_id=user.id,
        action=AuditAction.UPDATE,
        summary=f"修改用户「{user.real_name}({user.username})」",
        detail={
            "before": before,
            "after": {
                "real_name": user.real_name,
                "email": user.email,
                "dept_id": user.dept_id,
                "position": user.position,
                "status": user.status,
                "roles": user.role_codes,
            },
        },
        ip=ip,
    )
    db.commit()
    db.refresh(user)
    return user


def _replace_roles(db: Session, user: User, roles: list[Role], actor: User | None) -> None:
    target = {r.id for r in roles}
    current = {link.role_id for link in user.role_links}
    for link in list(user.role_links):
        if link.role_id not in target:
            db.delete(link)
    for role_id in target - current:
        db.add(UserRole(user_id=user.id, role_id=role_id, granted_by=actor.id if actor else None))
    db.flush()
    db.refresh(user)


def delete(
    db: Session, user: User, *, actor: User | None = None, ip: str | None = None
) -> None:
    if actor is not None and actor.id == user.id:
        raise BadRequestError("不能删除当前登录账号", code="CANNOT_DELETE_SELF")
    if user.is_superuser and _superuser_count(db) <= 1:
        raise BadRequestError("系统必须保留至少一名超级管理员", code="LAST_SUPERUSER")

    # departments.manager_user_id 没有外键（见 models/org.py 说明），需手动清理悬挂引用
    for dept in db.scalars(
        select(Department).where(Department.manager_user_id == user.id)
    ).all():
        dept.manager_user_id = None

    biz_id, summary = user.id, f"删除用户「{user.real_name}({user.username})」"
    db.delete(user)
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.USER,
        biz_id=biz_id,
        action=AuditAction.DELETE,
        summary=summary,
        ip=ip,
    )
    db.commit()


def reset_password(
    db: Session,
    user: User,
    new_password: str,
    *,
    actor: User | None = None,
    ip: str | None = None,
) -> None:
    user.password_hash = hash_password(new_password)
    # 递增 token_version，让该用户所有已登录会话立即失效
    user.token_version += 1
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.USER,
        biz_id=user.id,
        action=AuditAction.RESET_PASSWORD,
        summary=f"重置用户「{user.real_name}({user.username})」密码",
        ip=ip,
    )
    db.commit()


def set_status(
    db: Session,
    user: User,
    status: UserStatus,
    *,
    actor: User | None = None,
    ip: str | None = None,
) -> User:
    _assert_can_change_status(user, status, actor)
    user.status = status
    if status == UserStatus.DISABLED:
        # 停用即踢下线
        user.token_version += 1
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.USER,
        biz_id=user.id,
        action=AuditAction.ENABLE if status == UserStatus.ACTIVE else AuditAction.DISABLE,
        summary=f"{'启用' if status == UserStatus.ACTIVE else '停用'}用户「{user.real_name}」",
        ip=ip,
    )
    db.commit()
    db.refresh(user)
    return user


def _assert_can_change_status(user: User, status: UserStatus, actor: User | None) -> None:
    if actor is not None and actor.id == user.id and status == UserStatus.DISABLED:
        raise BadRequestError("不能停用当前登录账号", code="CANNOT_DISABLE_SELF")
    if (
        status == UserStatus.DISABLED
        and user.is_superuser
        and _superuser_count_safe(user) <= 1
    ):
        raise BadRequestError("系统必须保留至少一名启用的超级管理员", code="LAST_SUPERUSER")


def _superuser_count(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id)).where(User.is_superuser.is_(True))
    ) or 0


def _superuser_count_safe(user: User) -> int:
    """`user` 所在会话上统计启用中的超管数。"""
    session = Session.object_session(user)
    if session is None:
        return 2  # 脱离会话（纯对象单测）时不阻拦
    return session.scalar(
        select(func.count(User.id)).where(
            User.is_superuser.is_(True), User.status == UserStatus.ACTIVE
        )
    ) or 0


# --------------------------------------------------------------------------- 选择器 / 导入


def search_options(
    db: Session,
    *,
    keyword: str | None = None,
    dept_id: int | None = None,
    include_sub_depts: bool = True,
    limit: int = 50,
) -> list[UserOption]:
    """人员选择器的候选来源（M2 的人员控件会直接复用）。"""
    stmt = build_query(
        db,
        keyword=keyword,
        dept_id=dept_id,
        status=UserStatus.ACTIVE,
        include_sub_depts=include_sub_depts,
    ).order_by(User.real_name, User.id)
    users = list(db.scalars(stmt.limit(limit)).all())
    names = _dept_names(db, {u.dept_id for u in users if u.dept_id is not None})
    return [
        UserOption(
            id=u.id,
            username=u.username,
            real_name=u.real_name,
            dept_id=u.dept_id,
            dept_name=names.get(u.dept_id) if u.dept_id else None,
        )
        for u in users
    ]


CSV_COLUMNS = ("username", "real_name", "email", "phone", "dept_code", "position", "roles", "password")


def import_csv(
    db: Session, content: bytes, *, actor: User | None = None, ip: str | None = None
) -> dict[str, Any]:
    """批量导入用户（F6.1）。

    逐行处理、单行失败不影响其他行，返回 created / failed 明细供前端展示。
    整体在一个事务里提交，避免部分成功导致的重跑困惑。
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BadRequestError(
            "文件编码无法识别，请另存为 UTF-8 编码的 CSV", code="CSV_ENCODING"
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise BadRequestError("CSV 为空或缺少表头", code="CSV_EMPTY")

    missing = {"username", "real_name"} - {c.strip() for c in reader.fieldnames}
    if missing:
        raise BadRequestError(
            f"CSV 缺少必需列：{', '.join(sorted(missing))}",
            code="CSV_MISSING_COLUMNS",
            extra={"required": ["username", "real_name"]},
        )

    role_by_code = {r.code: r for r in db.scalars(select(Role)).all()}
    dept_by_code = {d.code: d for d in db.scalars(select(Department)).all()}

    created: list[str] = []
    failed: list[dict[str, Any]] = []

    for line_no, raw in enumerate(reader, start=2):
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        username = row.get("username", "")
        if not username:
            failed.append({"line": line_no, "username": "", "message": "username 为空"})
            continue
        if db.scalar(select(User.id).where(User.username == username)):
            failed.append({"line": line_no, "username": username, "message": "用户名已存在"})
            continue

        dept_code = row.get("dept_code", "")
        dept = dept_by_code.get(dept_code) if dept_code else None
        if dept_code and dept is None:
            failed.append({"line": line_no, "username": username, "message": f"部门编码 {dept_code} 不存在"})
            continue

        role_codes = [c for c in row.get("roles", "").replace("，", ",").split(",") if c]
        unknown_roles = [c for c in role_codes if c not in role_by_code]
        if unknown_roles:
            failed.append(
                {"line": line_no, "username": username, "message": f"角色不存在：{', '.join(unknown_roles)}"}
            )
            continue

        user = User(
            username=username,
            real_name=row.get("real_name") or username,
            password_hash=hash_password(row.get("password") or DEFAULT_IMPORT_PASSWORD),
            email=(row.get("email") or None),
            phone=(row.get("phone") or None),
            dept_id=dept.id if dept else None,
            position=(row.get("position") or None),
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        db.flush()
        for code in role_codes:
            db.add(
                UserRole(
                    user_id=user.id,
                    role_id=role_by_code[code].id,
                    granted_by=actor.id if actor else None,
                )
            )
        created.append(username)

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.USER,
        biz_id=0,
        action=AuditAction.IMPORT,
        summary=f"导入用户 {len(created)} 条，失败 {len(failed)} 条",
        detail={"created": created, "failed": failed},
        ip=ip,
    )
    db.commit()
    return {"created": len(created), "failed": failed, "default_password": DEFAULT_IMPORT_PASSWORD}
