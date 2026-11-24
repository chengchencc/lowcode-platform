"""组织数据导出 / 导入 —— 把一套「像真的」用户、部门、角色搬到别的环境。

用法（在 backend 目录或容器内）：

    python -m app.scripts.org_sync export -o org-data.json
    python -m app.scripts.org_sync import -i org-data.json --dry-run
    python -m app.scripts.org_sync import -i org-data.json

Docker 部署里更省事的入口见 `scripts/org-sync.sh`。

设计要点：

- **自然键搬运**：文件里只出现用户名、部门编码、角色编码，不出现自增 id；
  导入端按编码重新查/建，目标环境 id 不同也能正确落位。
- **密码原样搬运**：bcrypt hash 与环境无关，复制后在目标环境用原密码即可登录。
- **默认只补缺**：已存在的角色/部门/用户一律跳过，不覆盖目标环境的资料；
  需要对齐时显式加 ``--update``，连密码一起覆盖再加 ``--update-passwords``。
- **不搬附件**：`avatar` 只是存储路径，头像文件本身不在本脚本范围内。
- **单事务**：`import_payload` 只 flush 不 commit，由调用方决定提交或回滚，
  这样 ``--dry-run`` 与出错回滚的行为都可靠。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.constants import (
    AuditAction,
    AuditBizType,
    DeptStatus,
    RoleStatus,
    UserStatus,
)
from app.db.session import SessionLocal
from app.models import Department, Role, User, UserRole
from app.services import audit_service

#: 文件格式版本。字段只增不改时保持 1；破坏性变更再递增。
SCHEMA_VERSION = 1


@dataclass(slots=True)
class ImportReport:
    """导入结果统计与问题清单，供 CLI 打印。"""

    created: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    updated: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    skipped: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


# --------------------------------------------------------------------------- 导出


def export_payload(db: Session) -> dict[str, Any]:
    """把当前环境的组织数据导出为可搬运的 dict。"""
    roles = list(db.scalars(select(Role).order_by(Role.id)))
    depts = list(db.scalars(select(Department).order_by(Department.id)))
    users = list(db.scalars(select(User).order_by(User.id)))

    dept_by_id = {d.id: d for d in depts}
    user_by_id = {u.id: u for u in users}

    # 父部门排在子部门之前：即便导入端按数组顺序处理也能一次落位
    ordered_depts = sorted(depts, key=lambda d: (d.level, d.path, d.id))

    links: list[dict[str, str | None]] = []
    for user in users:
        for link in user.role_links:
            if link.role is None:
                continue
            granted_by = user_by_id.get(link.granted_by) if link.granted_by else None
            links.append(
                {
                    "username": user.username,
                    "role_code": link.role.code,
                    "granted_by": granted_by.username if granted_by else None,
                }
            )

    return {
        "version": SCHEMA_VERSION,
        "exported_at": utcnow().isoformat(timespec="seconds"),
        "roles": [
            {
                "code": r.code,
                "name": r.name,
                "description": r.description,
                "is_builtin": r.is_builtin,
                "status": str(r.status),
            }
            for r in roles
        ],
        "departments": [
            {
                "code": d.code,
                "name": d.name,
                "parent_code": dept_by_id[d.parent_id].code if d.parent_id in dept_by_id else None,
                "manager_username": (
                    user_by_id[d.manager_user_id].username
                    if d.manager_user_id in user_by_id
                    else None
                ),
                "sort_order": d.sort_order,
                "status": str(d.status),
            }
            for d in ordered_depts
        ],
        "users": [
            {
                "username": u.username,
                "password_hash": u.password_hash,
                "real_name": u.real_name,
                "email": u.email,
                "phone": u.phone,
                "avatar": u.avatar,
                "dept_code": dept_by_id[u.dept_id].code if u.dept_id in dept_by_id else None,
                "position": u.position,
                "status": str(u.status),
                "is_superuser": u.is_superuser,
            }
            for u in users
        ],
        "user_roles": links,
    }


# --------------------------------------------------------------------------- 导入


def _key(value: Any) -> str:
    return str(value or "").strip().lower()


def _norm_status(value: Any, enum_cls: type, default: str) -> str:
    text = str(value or "").strip()
    return text if text in {str(item) for item in enum_cls} else default


def _audit(
    db: Session, *, biz_type: AuditBizType, biz_id: int, action: AuditAction, summary: str
) -> None:
    audit_service.record(
        db,
        actor=None,
        biz_type=biz_type,
        biz_id=biz_id,
        action=action,
        summary=summary,
        detail={"source": "org_sync"},
    )


def _import_roles(
    db: Session, items: list[dict[str, Any]], *, update: bool, report: ImportReport
) -> dict[str, Role]:
    by_code = {_key(r.code): r for r in db.scalars(select(Role))}
    for item in items:
        code = str(item.get("code") or "").strip()
        if not code:
            report.fail("角色缺少 code，已跳过")
            continue
        name = str(item.get("name") or code).strip()
        role = by_code.get(code.lower())
        if role is None:
            role = Role(
                code=code,
                name=name,
                description=item.get("description"),
                is_builtin=bool(item.get("is_builtin", False)),
                status=_norm_status(item.get("status"), RoleStatus, RoleStatus.ACTIVE),
            )
            db.add(role)
            db.flush()
            by_code[code.lower()] = role
            report.created["角色"] += 1
            _audit(
                db,
                biz_type=AuditBizType.ROLE,
                biz_id=role.id,
                action=AuditAction.CREATE,
                summary=f"组织数据导入：新建角色 {name}",
            )
            continue

        if not update:
            report.skipped["角色"] += 1
            continue

        changed = False
        for attr, value in (
            ("name", name),
            ("description", item.get("description")),
            ("status", _norm_status(item.get("status"), RoleStatus, role.status)),
        ):
            if getattr(role, attr) != value:
                setattr(role, attr, value)
                changed = True
        if changed:
            report.updated["角色"] += 1
            _audit(
                db,
                biz_type=AuditBizType.ROLE,
                biz_id=role.id,
                action=AuditAction.UPDATE,
                summary=f"组织数据导入：更新角色 {name}",
            )
        else:
            report.skipped["角色"] += 1
    return by_code


def _import_departments(
    db: Session, items: list[dict[str, Any]], *, update: bool, report: ImportReport
) -> tuple[dict[str, Department], list[tuple[Department, str | None]]]:
    """建部门。父部门可能排在数组后面，所以按「能落就先落」的方式多轮推进。"""
    by_code = {_key(d.code): d for d in db.scalars(select(Department))}

    pending: dict[str, dict[str, Any]] = {}
    for item in items:
        code = str(item.get("code") or "").strip()
        if not code:
            report.fail("部门缺少 code，已跳过")
            continue
        key = code.lower()
        if key in pending:
            report.fail(f"部门编码重复：{code}，后一条已跳过")
            continue
        pending[key] = {**item, "code": code}

    managers: list[tuple[Department, str | None]] = []

    while pending:
        progressed = False
        for key in list(pending):
            item = pending[key]
            code = item["code"]
            parent_code = str(item.get("parent_code") or "").strip()
            parent_key = parent_code.lower()

            if parent_key and parent_key not in by_code:
                if parent_key in pending:
                    continue  # 父部门在后面，等下一轮
                report.fail(f"部门 {code} 的父部门 {parent_code} 不存在，已跳过")
                del pending[key]
                progressed = True
                continue

            parent = by_code.get(parent_key) if parent_key else None
            dept = by_code.get(key)
            name = str(item.get("name") or code).strip()

            if dept is None:
                dept = Department(
                    code=code,
                    name=name,
                    parent_id=parent.id if parent else None,
                    level=(parent.level + 1) if parent else 1,
                    sort_order=int(item.get("sort_order") or 0),
                    status=_norm_status(item.get("status"), DeptStatus, DeptStatus.ACTIVE),
                )
                db.add(dept)
                db.flush()
                # 物化路径要等自增 id 出来；整棵树最后还会统一重算一次
                dept.path = f"{parent.path if parent else '/'}{dept.id}/"
                by_code[key] = dept
                report.created["部门"] += 1
                _audit(
                    db,
                    biz_type=AuditBizType.DEPT,
                    biz_id=dept.id,
                    action=AuditAction.CREATE,
                    summary=f"组织数据导入：新建部门 {name}",
                )
            elif update:
                changed = False
                for attr, value in (
                    ("name", name),
                    ("sort_order", int(item.get("sort_order") or 0)),
                    ("status", _norm_status(item.get("status"), DeptStatus, dept.status)),
                    ("parent_id", parent.id if parent else None),
                ):
                    if getattr(dept, attr) != value:
                        setattr(dept, attr, value)
                        changed = True
                if changed:
                    report.updated["部门"] += 1
                    _audit(
                        db,
                        biz_type=AuditBizType.DEPT,
                        biz_id=dept.id,
                        action=AuditAction.UPDATE,
                        summary=f"组织数据导入：更新部门 {name}",
                    )
                else:
                    report.skipped["部门"] += 1
            else:
                report.skipped["部门"] += 1

            managers.append((dept, str(item.get("manager_username") or "").strip() or None))
            del pending[key]
            progressed = True

        if not progressed:
            for item in pending.values():
                report.fail(f"部门 {item['code']} 的父部门链存在循环，已跳过")
            pending.clear()

    _rebuild_dept_paths(db)
    return by_code, managers


def _rebuild_dept_paths(db: Session) -> None:
    """按实际 parent_id 重算整棵树的 path / level。

    导入端的部门 id 与源环境不同，照抄 path 一定是错的；统一重算最稳妥，
    顺带修复目标环境里已有的路径漂移。
    """
    depts = list(db.scalars(select(Department)))
    by_id = {d.id: d for d in depts}
    cache: dict[int, tuple[str, int]] = {}

    def resolve(dept: Department, visiting: frozenset[int]) -> tuple[str, int]:
        if dept.id in cache:
            return cache[dept.id]
        if dept.id in visiting:
            raise ValueError(f"部门层级存在循环：{dept.code}")
        parent = by_id.get(dept.parent_id) if dept.parent_id else None
        if parent is None:
            result = (f"/{dept.id}/", 1)
        else:
            parent_path, parent_level = resolve(parent, visiting | {dept.id})
            result = (f"{parent_path}{dept.id}/", parent_level + 1)
        cache[dept.id] = result
        return result

    for dept in depts:
        path, level = resolve(dept, frozenset())
        if dept.path != path:
            dept.path = path
        if dept.level != level:
            dept.level = level


def _import_users(
    db: Session,
    items: list[dict[str, Any]],
    depts: dict[str, Department],
    *,
    update: bool,
    update_passwords: bool,
    report: ImportReport,
) -> dict[str, User]:
    by_username = {_key(u.username): u for u in db.scalars(select(User))}
    by_email = {_key(u.email): u for u in db.scalars(select(User)) if u.email}

    for item in items:
        username = str(item.get("username") or "").strip()
        if not username:
            report.fail("用户缺少 username，已跳过")
            continue

        user = by_username.get(username.lower())
        email = str(item.get("email") or "").strip() or None
        owner = by_email.get(_key(email)) if email else None
        if owner is not None and (user is None or owner.id != user.id):
            report.fail(f"用户 {username} 的邮箱 {email} 已被 {owner.username} 使用，已跳过")
            continue

        dept_code = str(item.get("dept_code") or "").strip()
        dept = depts.get(dept_code.lower()) if dept_code else None
        if dept_code and dept is None:
            report.warn(f"用户 {username} 的部门编码 {dept_code} 不存在，按无部门处理")

        password_hash = str(item.get("password_hash") or "").strip()
        profile = {
            "real_name": str(item.get("real_name") or username).strip(),
            "email": email,
            "phone": str(item.get("phone") or "").strip() or None,
            "avatar": str(item.get("avatar") or "").strip() or None,
            "dept_id": dept.id if dept else None,
            "position": str(item.get("position") or "").strip() or None,
            "status": _norm_status(item.get("status"), UserStatus, UserStatus.ACTIVE),
            "is_superuser": bool(item.get("is_superuser", False)),
        }

        if user is None:
            if not password_hash:
                report.fail(f"用户 {username} 缺少 password_hash，已跳过")
                continue
            user = User(username=username, password_hash=password_hash, **profile)
            db.add(user)
            db.flush()
            by_username[username.lower()] = user
            if email:
                by_email[_key(email)] = user
            report.created["用户"] += 1
            _audit(
                db,
                biz_type=AuditBizType.USER,
                biz_id=user.id,
                action=AuditAction.CREATE,
                summary=f"组织数据导入：新建用户 {username}",
            )
            continue

        changed = False
        if update:
            for attr, value in profile.items():
                if getattr(user, attr) != value:
                    setattr(user, attr, value)
                    changed = True
        if update_passwords and password_hash and user.password_hash != password_hash:
            user.password_hash = password_hash
            changed = True

        if changed:
            report.updated["用户"] += 1
            _audit(
                db,
                biz_type=AuditBizType.USER,
                biz_id=user.id,
                action=AuditAction.UPDATE,
                summary=f"组织数据导入：更新用户 {username}",
            )
        else:
            report.skipped["用户"] += 1
    return by_username


def _import_user_roles(
    db: Session,
    items: list[dict[str, Any]],
    users: dict[str, User],
    roles: dict[str, Role],
    *,
    replace_roles: bool,
    replace_for: set[str],
    report: ImportReport,
) -> None:
    desired: dict[int, set[int]] = defaultdict(set)
    granted_by: dict[tuple[int, int], int | None] = {}

    for item in items:
        username = str(item.get("username") or "").strip()
        role_code = str(item.get("role_code") or "").strip()
        user = users.get(username.lower())
        role = roles.get(role_code.lower())
        if user is None or role is None:
            missing = f"用户 {username}" if user is None else f"角色 {role_code}"
            report.fail(f"用户角色无法落位：{missing} 不存在（{username} / {role_code}）")
            continue

        desired[user.id].add(role.id)
        grantor = users.get(_key(item.get("granted_by")))
        granted_by[(user.id, role.id)] = grantor.id if grantor else None

    # --replace-roles 要覆盖「文件里出现过、但一个角色都没配」的用户，
    # 所以目标集合不只取 desired，还并入文件 users 列表里的所有用户名。
    targets = set(desired)
    if replace_roles:
        targets |= {users[key].id for key in replace_for if key in users}

    for user_id in targets:
        role_ids = desired.get(user_id, set())
        existing = list(db.scalars(select(UserRole).where(UserRole.user_id == user_id)))
        existing_role_ids = {link.role_id for link in existing}
        for role_id in role_ids:
            if role_id in existing_role_ids:
                report.skipped["用户角色"] += 1
                continue
            db.add(
                UserRole(
                    user_id=user_id,
                    role_id=role_id,
                    granted_by=granted_by.get((user_id, role_id)),
                )
            )
            report.created["用户角色"] += 1

        if replace_roles:
            for link in existing:
                if link.role_id not in role_ids:
                    db.delete(link)
                    report.updated["用户角色"] += 1


def _apply_managers(
    db: Session,
    managers: list[tuple[Department, str | None]],
    users: dict[str, User],
    *,
    update: bool,
    report: ImportReport,
) -> None:
    for dept, username in managers:
        if not username:
            if update and dept.manager_user_id is not None:
                dept.manager_user_id = None
                report.updated["部门主管"] += 1
            continue

        user = users.get(username.lower())
        if user is None:
            report.warn(f"部门 {dept.code} 的主管 {username} 不存在，未设置")
            continue

        if dept.manager_user_id == user.id:
            report.skipped["部门主管"] += 1
        elif dept.manager_user_id is None or update:
            dept.manager_user_id = user.id
            report.updated["部门主管"] += 1
        else:
            report.skipped["部门主管"] += 1


def import_payload(
    db: Session,
    payload: dict[str, Any],
    *,
    update: bool = False,
    update_passwords: bool = False,
    replace_roles: bool = False,
) -> ImportReport:
    """把导出的组织数据写入当前库。

    **只 flush、不 commit**：调用方负责提交；失败时回滚整个事务即可，
    不会留下半套数据。`--dry-run` 也就是「跑完后回滚」。
    """
    version = int(payload.get("version") or 0)
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"文件格式版本 {version} 高于当前脚本支持的 {SCHEMA_VERSION}，请先升级后端"
        )

    report = ImportReport()
    roles = _import_roles(db, list(payload.get("roles") or []), update=update, report=report)
    depts, managers = _import_departments(
        db, list(payload.get("departments") or []), update=update, report=report
    )
    user_items = list(payload.get("users") or [])
    users = _import_users(
        db,
        user_items,
        depts,
        update=update,
        update_passwords=update_passwords,
        report=report,
    )
    imported_usernames = {_key(item.get("username")) for item in user_items if item.get("username")}
    _import_user_roles(
        db,
        list(payload.get("user_roles") or []),
        users,
        roles,
        replace_roles=replace_roles,
        replace_for=imported_usernames,
        report=report,
    )
    _apply_managers(db, managers, users, update=update, report=report)
    db.flush()
    return report


# --------------------------------------------------------------------------- CLI


def _print_report(report: ImportReport) -> None:
    def line(label: str, counts: dict[str, int]) -> None:
        if counts:
            detail = "、".join(f"{k} {v}" for k, v in counts.items())
            print(f"{label}：{detail}")

    line("已创建", report.created)
    line("已更新", report.updated)
    line("已跳过", report.skipped)
    if report.warnings:
        print(f"警告 {len(report.warnings)} 条：")
        for message in report.warnings:
            print(f"  - {message}")
    if report.failures:
        print(f"失败 {len(report.failures)} 条：")
        for message in report.failures:
            print(f"  - {message}")


def _read_payload(path: Path | None) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path else sys.stdin.read()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("文件内容不是 JSON 对象")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="导出 / 导入组织数据（用户、部门、角色），用于在环境间搬运测试数据"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="导出当前环境的组织数据")
    p_export.add_argument("-o", "--output", type=Path, help="输出文件（默认写到标准输出）")

    p_import = sub.add_parser("import", help="把文件导入当前环境")
    p_import.add_argument("-i", "--input", type=Path, help="输入文件（默认从标准输入读取）")
    p_import.add_argument("--dry-run", action="store_true", help="演练：跑完回滚，不写库")
    p_import.add_argument(
        "--update", action="store_true", help="覆盖已存在的角色/部门/用户资料（不含密码）"
    )
    p_import.add_argument(
        "--update-passwords",
        action="store_true",
        help="同时用文件里的密码 hash 覆盖已存在用户（复制登录密码时必须）",
    )
    p_import.add_argument(
        "--replace-roles",
        action="store_true",
        help="按文件覆盖用户的角色集合（会移除文件里没有的角色）",
    )

    args = parser.parse_args(argv)

    if args.command == "export":
        with SessionLocal() as db:
            payload = export_payload(db)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
            counts = {
                "角色": len(payload["roles"]),
                "部门": len(payload["departments"]),
                "用户": len(payload["users"]),
                "用户角色": len(payload["user_roles"]),
            }
            detail = "、".join(f"{k} {v}" for k, v in counts.items())
            print(f"已导出到 {args.output}（{detail}）")
        else:
            sys.stdout.write(text)
        return 0

    payload = _read_payload(args.input)
    with SessionLocal() as db:
        try:
            report = import_payload(
                db,
                payload,
                update=args.update,
                update_passwords=args.update_passwords,
                replace_roles=args.replace_roles,
            )
            if args.dry_run:
                db.rollback()
                print("演练完成（已回滚，未写库）：")
            else:
                db.commit()
        except Exception:
            db.rollback()
            raise
    _print_report(report)
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
