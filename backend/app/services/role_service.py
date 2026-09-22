"""角色管理（F6.3）。

角色是「审批人解析」与「发起范围控制」的依据（PRD §2 补充规则），
因此内置角色的 code 被上游流程定义直接引用，禁止改名/删除。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import AuditAction, AuditBizType, RoleStatus
from app.core.errors import ConflictError, NotFoundError
from app.models import Role, User, UserRole
from app.schemas.org import RoleCreate, RoleOut, RoleUpdate
from app.services import audit_service


def get_or_404(db: Session, role_id: int) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise NotFoundError("角色不存在", code="ROLE_NOT_FOUND")
    return role


def _member_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(UserRole.role_id, func.count(UserRole.id)).group_by(UserRole.role_id)
    ).all()
    return {role_id: count for role_id, count in rows}


def list_roles(
    db: Session, *, keyword: str | None = None, status: str | None = None
) -> list[RoleOut]:
    stmt = select(Role).order_by(Role.is_builtin.desc(), Role.id)
    if status:
        stmt = stmt.where(Role.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Role.name.like(like) | Role.code.like(like))

    roles = list(db.scalars(stmt).all())
    counts = _member_counts(db)
    return [
        RoleOut(
            id=r.id,
            code=r.code,
            name=r.name,
            description=r.description,
            is_builtin=r.is_builtin,
            status=r.status,
            member_count=counts.get(r.id, 0),
            created_at=r.created_at,
        )
        for r in roles
    ]


def to_out(db: Session, role: Role) -> RoleOut:
    count = db.scalar(
        select(func.count(UserRole.id)).where(UserRole.role_id == role.id)
    ) or 0
    return RoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_builtin=role.is_builtin,
        status=role.status,
        member_count=count,
        created_at=role.created_at,
    )


def resolve_ids(db: Session, role_ids: list[int]) -> list[Role]:
    """校验角色 id 全部存在，返回角色列表（用于用户保存时的 role_ids 校验）。"""
    if not role_ids:
        return []
    unique_ids = list(dict.fromkeys(role_ids))
    roles = list(db.scalars(select(Role).where(Role.id.in_(unique_ids))).all())
    missing = set(unique_ids) - {r.id for r in roles}
    if missing:
        raise NotFoundError(f"角色不存在：{sorted(missing)}", code="ROLE_NOT_FOUND")
    return roles


def create(
    db: Session, payload: RoleCreate, *, actor: User | None = None, ip: str | None = None
) -> Role:
    if db.scalar(select(Role.id).where(Role.code == payload.code)):
        raise ConflictError(f"角色标识 {payload.code} 已存在", code="ROLE_CODE_EXISTS")
    role = Role(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        is_builtin=False,
    )
    db.add(role)
    db.flush()
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.ROLE,
        biz_id=role.id,
        action=AuditAction.CREATE,
        summary=f"新建角色「{role.name}」",
        detail={"code": role.code, "name": role.name},
        ip=ip,
    )
    db.commit()
    db.refresh(role)
    return role


def update(
    db: Session,
    role: Role,
    payload: RoleUpdate,
    *,
    actor: User | None = None,
    ip: str | None = None,
) -> Role:
    if payload.name is not None:
        role.name = payload.name
    if "description" in payload.model_fields_set:
        role.description = payload.description
    if payload.status is not None:
        if role.is_builtin and payload.status == RoleStatus.DISABLED:
            raise ConflictError("内置角色不可停用", code="ROLE_BUILTIN_PROTECTED")
        role.status = payload.status

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.ROLE,
        biz_id=role.id,
        action=AuditAction.UPDATE,
        summary=f"修改角色「{role.name}」",
        ip=ip,
    )
    db.commit()
    db.refresh(role)
    return role


def delete(
    db: Session, role: Role, *, actor: User | None = None, ip: str | None = None
) -> None:
    if role.is_builtin:
        raise ConflictError("内置角色不可删除", code="ROLE_BUILTIN_PROTECTED")

    member_count = db.scalar(
        select(func.count(UserRole.id)).where(UserRole.role_id == role.id)
    ) or 0
    if member_count:
        raise ConflictError(
            f"该角色下还有 {member_count} 名成员，请先移除成员",
            code="ROLE_HAS_MEMBERS",
            extra={"member_count": member_count},
        )

    biz_id, name = role.id, role.name
    db.delete(role)
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.ROLE,
        biz_id=biz_id,
        action=AuditAction.DELETE,
        summary=f"删除角色「{name}」",
        ip=ip,
    )
    db.commit()


def list_members(db: Session, role: Role) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role_id == role.id)
            .order_by(User.status, User.real_name)
        ).all()
    )


def set_members(
    db: Session, role: Role, user_ids: list[int], *, actor: User | None = None
) -> None:
    """整体覆盖角色成员。"""
    target_ids = set(user_ids)
    if target_ids:
        found = set(db.scalars(select(User.id).where(User.id.in_(target_ids))).all())
        missing = target_ids - found
        if missing:
            raise NotFoundError(f"用户不存在：{sorted(missing)}", code="USER_NOT_FOUND")

    current = set(
        db.scalars(select(UserRole.user_id).where(UserRole.role_id == role.id)).all()
    )

    for user_id in target_ids - current:
        db.add(UserRole(user_id=user_id, role_id=role.id, granted_by=actor.id if actor else None))
    for link in db.scalars(
        select(UserRole).where(
            UserRole.role_id == role.id, UserRole.user_id.in_(current - target_ids)
        )
    ).all():
        db.delete(link)

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.ROLE,
        biz_id=role.id,
        action=AuditAction.UPDATE,
        summary=f"调整角色「{role.name}」成员",
        detail={"added": sorted(target_ids - current), "removed": sorted(current - target_ids)},
    )
    db.commit()
