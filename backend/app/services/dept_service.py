"""部门管理（F6.2）。树形结构的读写与物化路径维护。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import AuditAction, AuditBizType, DeptStatus, UserStatus
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.models import Department, User
from app.schemas.org import DeptCreate, DeptMemberOut, DeptOut, DeptUpdate
from app.services import audit_service


def get_or_404(db: Session, dept_id: int) -> Department:
    dept = db.get(Department, dept_id)
    if dept is None:
        raise NotFoundError("部门不存在", code="DEPT_NOT_FOUND")
    return dept


def list_all(db: Session, *, status: str | None = None) -> list[Department]:
    stmt = select(Department).order_by(Department.sort_order, Department.id)
    if status:
        stmt = stmt.where(Department.status == status)
    return list(db.scalars(stmt).all())


def descendant_ids(db: Session, dept: Department, *, include_self: bool = False) -> list[int]:
    """子树 id 列表（不含自身）。物化路径的直接收益：一条 LIKE 搞定。"""
    stmt = select(Department.id).where(Department.path.like(f"{dept.path}%"))
    if not include_self:
        stmt = stmt.where(Department.id != dept.id)
    return [row for row in db.scalars(stmt).all()]


def ancestor_ids(db: Session, dept: Department) -> list[int]:
    """从根到父节点的祖先 id 列表，按层级升序。"""
    parts = [p for p in dept.path.split("/") if p and int(p) != dept.id]
    if not parts:
        return []
    ids = [int(p) for p in parts]
    rows = db.scalars(select(Department.id).where(Department.id.in_(ids))).all()
    present = set(rows)
    return [i for i in ids if i in present]


# --------------------------------------------------------------------------- 树装配


def _member_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(User.dept_id, func.count(User.id))
        .where(User.dept_id.is_not(None))
        .group_by(User.dept_id)
    ).all()
    return {dept_id: count for dept_id, count in rows}


def _manager_names(db: Session, manager_ids: set[int]) -> dict[int, str]:
    if not manager_ids:
        return {}
    rows = db.execute(
        select(User.id, User.real_name).where(User.id.in_(manager_ids))
    ).all()
    return {uid: name for uid, name in rows}


def build_tree(db: Session, *, status: str | None = None) -> list[DeptOut]:
    """把扁平部门列表装配成树，一次性补齐 member_count 与主管姓名（避免 N+1）。"""
    depts = list_all(db, status=status)
    counts = _member_counts(db)
    names = _manager_names(
        db, {d.manager_user_id for d in depts if d.manager_user_id is not None}
    )

    nodes: dict[int, DeptOut] = {}
    for d in depts:
        nodes[d.id] = DeptOut(
            id=d.id,
            name=d.name,
            code=d.code,
            parent_id=d.parent_id,
            path=d.path,
            level=d.level,
            manager_user_id=d.manager_user_id,
            manager_name=names.get(d.manager_user_id) if d.manager_user_id else None,
            sort_order=d.sort_order,
            status=d.status,
            member_count=counts.get(d.id, 0),
        )

    roots: list[DeptOut] = []
    for d in depts:
        node = nodes[d.id]
        parent = nodes.get(d.parent_id) if d.parent_id else None
        # 父节点被过滤掉（如按 status 过滤）时，该节点提升为根，避免整棵子树消失
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    return roots


def to_out(db: Session, dept: Department) -> DeptOut:
    counts = _member_counts(db)
    names = _manager_names(
        db, {dept.manager_user_id} if dept.manager_user_id else set()
    )
    return DeptOut(
        id=dept.id,
        name=dept.name,
        code=dept.code,
        parent_id=dept.parent_id,
        path=dept.path,
        level=dept.level,
        manager_user_id=dept.manager_user_id,
        manager_name=names.get(dept.manager_user_id) if dept.manager_user_id else None,
        sort_order=dept.sort_order,
        status=dept.status,
        member_count=counts.get(dept.id, 0),
    )


# --------------------------------------------------------------------------- 写


def create(
    db: Session, payload: DeptCreate, *, actor: User | None = None, ip: str | None = None
) -> Department:
    if db.scalar(select(Department.id).where(Department.code == payload.code)):
        raise ConflictError(f"部门编码 {payload.code} 已存在", code="DEPT_CODE_EXISTS")

    parent: Department | None = None
    if payload.parent_id is not None:
        parent = get_or_404(db, payload.parent_id)
        if parent.status == DeptStatus.DISABLED:
            raise BadRequestError("不能在已停用的部门下新建子部门", code="PARENT_DISABLED")

    _assert_manager_valid(db, payload.manager_user_id)

    dept = Department(
        name=payload.name,
        code=payload.code,
        parent_id=payload.parent_id,
        manager_user_id=payload.manager_user_id,
        sort_order=payload.sort_order,
        status=payload.status,
        level=(parent.level + 1) if parent else 1,
    )
    db.add(dept)
    # 物化路径需要自身 id，只能先 flush 拿到自增主键再回填
    db.flush()
    dept.path = f"{parent.path if parent else '/'}{dept.id}/"

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.DEPT,
        biz_id=dept.id,
        action=AuditAction.CREATE,
        summary=f"新建部门「{dept.name}」",
        detail={"name": dept.name, "code": dept.code, "parent_id": dept.parent_id},
        ip=ip,
    )
    db.commit()
    db.refresh(dept)
    return dept


def update(
    db: Session,
    dept: Department,
    payload: DeptUpdate,
    *,
    actor: User | None = None,
    ip: str | None = None,
) -> Department:
    before = {
        "name": dept.name,
        "parent_id": dept.parent_id,
        "manager_user_id": dept.manager_user_id,
        "sort_order": dept.sort_order,
        "status": dept.status,
    }
    parent_changed = (
        "parent_id" in payload.model_fields_set and payload.parent_id != dept.parent_id
    )

    if "manager_user_id" in payload.model_fields_set:
        _assert_manager_valid(db, payload.manager_user_id)
        dept.manager_user_id = payload.manager_user_id

    if payload.name is not None:
        dept.name = payload.name
    if payload.sort_order is not None:
        dept.sort_order = payload.sort_order
    if payload.status is not None:
        dept.status = payload.status

    if parent_changed:
        _move(db, dept, payload.parent_id)

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.DEPT,
        biz_id=dept.id,
        action=AuditAction.UPDATE,
        summary=f"修改部门「{dept.name}」",
        detail={"before": before, "after": {"name": dept.name, "parent_id": dept.parent_id}},
        ip=ip,
    )
    db.commit()
    db.refresh(dept)
    return dept


def _move(db: Session, dept: Department, new_parent_id: int | None) -> None:
    """调整父节点，并同步整棵子树的 path / level。"""
    if new_parent_id == dept.id:
        raise BadRequestError("不能把部门设为自己的上级", code="DEPT_PARENT_SELF")

    new_parent: Department | None = None
    if new_parent_id is not None:
        new_parent = get_or_404(db, new_parent_id)
        # 移动到自己的子孙下会形成环，path 会无限增长
        if new_parent.path.startswith(dept.path):
            raise BadRequestError("不能把部门移动到自己的子部门下", code="DEPT_PARENT_CYCLE")

    old_path = dept.path
    new_path = f"{new_parent.path if new_parent else '/'}{dept.id}/"
    level_delta = ((new_parent.level + 1) if new_parent else 1) - dept.level

    dept.parent_id = new_parent_id
    dept.path = new_path
    dept.level += level_delta

    # 子树整体平移：path 前缀替换 + level 偏移
    for child in db.scalars(
        select(Department).where(Department.path.like(f"{old_path}%"))
    ).all():
        if child.id == dept.id:
            continue
        child.path = new_path + child.path[len(old_path) :]
        child.level += level_delta


def delete(
    db: Session, dept: Department, *, actor: User | None = None, ip: str | None = None
) -> None:
    if descendant_ids(db, dept):
        raise ConflictError("该部门下还有子部门，请先处理子部门", code="DEPT_HAS_CHILDREN")
    member_count = db.scalar(
        select(func.count(User.id)).where(User.dept_id == dept.id)
    ) or 0
    if member_count:
        raise ConflictError(
            f"该部门下还有 {member_count} 名成员，请先移除成员",
            code="DEPT_HAS_MEMBERS",
            extra={"member_count": member_count},
        )

    biz_id, name = dept.id, dept.name
    db.delete(dept)
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.DEPT,
        biz_id=biz_id,
        action=AuditAction.DELETE,
        summary=f"删除部门「{name}」",
        ip=ip,
    )
    db.commit()


# --------------------------------------------------------------------------- 成员


def list_members(db: Session, dept: Department) -> list[DeptMemberOut]:
    rows = db.scalars(
        select(User)
        .where(User.dept_id == dept.id)
        .order_by(User.status, User.real_name)
    ).all()
    return [
        DeptMemberOut(
            id=u.id,
            username=u.username,
            real_name=u.real_name,
            position=u.position,
            status=u.status,
        )
        for u in rows
    ]


def set_members(
    db: Session, dept: Department, user_ids: list[int], *, actor: User | None = None
) -> None:
    """整体覆盖该部门成员：把 user_ids 移入本部门，把原属本部门但不在列表里的移出。"""
    target_ids = set(user_ids)
    if target_ids:
        found = set(
            db.scalars(select(User.id).where(User.id.in_(target_ids))).all()
        )
        missing = target_ids - found
        if missing:
            raise NotFoundError(
                f"用户不存在：{sorted(missing)}", code="USER_NOT_FOUND"
            )

    current = set(
        db.scalars(select(User.id).where(User.dept_id == dept.id)).all()
    )

    if target_ids - current:
        for user in db.scalars(select(User).where(User.id.in_(target_ids - current))).all():
            user.dept_id = dept.id
    if current - target_ids:
        for user in db.scalars(select(User).where(User.id.in_(current - target_ids))).all():
            user.dept_id = None

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.DEPT,
        biz_id=dept.id,
        action=AuditAction.UPDATE,
        summary=f"调整部门「{dept.name}」成员",
        detail={"added": sorted(target_ids - current), "removed": sorted(current - target_ids)},
    )
    db.commit()


def _assert_manager_valid(db: Session, manager_user_id: int | None) -> None:
    """部门主管必须是存在的、启用中的用户（PRD §3.3.2 审批人解析的前置条件）。"""
    if manager_user_id is None:
        return
    user = db.get(User, manager_user_id)
    if user is None:
        raise NotFoundError("指定为部门主管的用户不存在", code="MANAGER_NOT_FOUND")
    if user.status != UserStatus.ACTIVE:
        raise BadRequestError("已停用的用户不能担任部门主管", code="MANAGER_DISABLED")
