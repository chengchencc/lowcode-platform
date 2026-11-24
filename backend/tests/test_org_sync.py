"""组织数据导出 / 导入（`app.scripts.org_sync`）。

覆盖三件事：导出内容是否用自然键、删除后能否原样还原（含密码与部门主管）、
重复导入是否幂等。
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.constants import DeptStatus, RoleCode, UserStatus
from app.core.security import hash_password, verify_password
from app.models import Department, Role, User, UserRole
from app.scripts.org_sync import export_payload, import_payload

QA_PASSWORD = "Qa@123456"


def _make_qa_org(db) -> tuple[Department, Role, User]:
    """造一套不属于种子数据的「真实感」组织，便于验证增量的往返。"""
    hq = db.scalar(select(Department).where(Department.code == "HQ"))
    assert hq is not None
    admin = db.scalar(select(User).where(User.is_superuser.is_(True)))
    assert admin is not None

    role = Role(code="qa_lead", name="质量负责人", description="测试环境专有角色")
    db.add(role)
    db.flush()

    dept = Department(
        name="质量保障部",
        code="QA",
        parent_id=hq.id,
        level=hq.level + 1,
        status=DeptStatus.ACTIVE,
    )
    db.add(dept)
    db.flush()
    dept.path = f"{hq.path}{dept.id}/"

    user = User(
        username="qa01",
        real_name="测试员甲",
        password_hash=hash_password(QA_PASSWORD),
        dept_id=dept.id,
        position="测试工程师",
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id, granted_by=admin.id))
    dept.manager_user_id = user.id
    db.commit()
    return dept, role, user


def _remove_qa_org(db, dept: Department, role: Role, user: User) -> None:
    db.delete(db.scalar(select(UserRole).where(UserRole.user_id == user.id)))
    db.delete(user)
    db.flush()
    db.delete(dept)
    db.flush()
    db.delete(role)
    db.commit()


def test_export_uses_natural_keys(db):
    dept, role, user = _make_qa_org(db)

    payload = export_payload(db)

    assert payload["version"] == 1
    assert any(r["code"] == RoleCode.PLATFORM_ADMIN for r in payload["roles"])

    exported_depts = {d["code"]: d for d in payload["departments"]}
    assert exported_depts["QA"]["parent_code"] == "HQ"
    assert exported_depts["QA"]["manager_username"] == "qa01"
    assert exported_depts["TECH"]["parent_code"] == "HQ"

    exported_users = {u["username"]: u for u in payload["users"]}
    assert exported_users["qa01"]["dept_code"] == "QA"
    assert exported_users["qa01"]["password_hash"] == user.password_hash

    qa_links = [link for link in payload["user_roles"] if link["username"] == "qa01"]
    assert qa_links == [{"username": "qa01", "role_code": "qa_lead", "granted_by": "admin"}]

    # 父部门必须排在子部门前面
    codes = [d["code"] for d in payload["departments"]]
    assert codes.index("HQ") < codes.index("QA")


def test_import_restores_deleted_org_data(db):
    dept, role, user = _make_qa_org(db)
    payload = export_payload(db)
    _remove_qa_org(db, dept, role, user)

    assert db.scalar(select(User).where(User.username == "qa01")) is None

    report = import_payload(db, payload)
    db.commit()

    restored_role = db.scalar(select(Role).where(Role.code == "qa_lead"))
    restored_dept = db.scalar(select(Department).where(Department.code == "QA"))
    restored_user = db.scalar(select(User).where(User.username == "qa01"))
    assert restored_role is not None and restored_role.name == "质量负责人"
    assert restored_dept is not None
    assert restored_user is not None

    # id 与源环境不同，但关系必须重新接对
    hq = db.scalar(select(Department).where(Department.code == "HQ"))
    assert restored_dept.parent_id == hq.id
    assert restored_dept.path == f"{hq.path}{restored_dept.id}/"
    assert restored_dept.level == hq.level + 1
    assert restored_dept.manager_user_id == restored_user.id
    assert restored_user.dept_id == restored_dept.id
    assert verify_password(QA_PASSWORD, restored_user.password_hash)

    link = db.scalar(
        select(UserRole).where(
            UserRole.user_id == restored_user.id,
            UserRole.role_id == restored_role.id,
        )
    )
    assert link is not None
    assert link.granted_by == db.scalar(select(User.id).where(User.username == "admin"))

    assert report.created["角色"] == 1
    assert report.created["部门"] == 1
    assert report.created["用户"] == 1
    assert report.created["用户角色"] == 1
    assert report.updated["部门主管"] == 1
    assert not report.failures


def test_import_is_idempotent(db):
    dept, role, user = _make_qa_org(db)
    payload = export_payload(db)
    _remove_qa_org(db, dept, role, user)

    import_payload(db, payload)
    db.commit()

    second = import_payload(db, payload)
    db.commit()

    assert not second.created
    assert second.skipped["角色"] >= 1
    assert second.skipped["部门"] >= 1
    assert second.skipped["用户"] >= 1
    assert db.scalar(select(User).where(User.username == "qa01")) is not None
    assert db.scalar(select(Role).where(Role.code == "qa_lead")) is not None


def test_update_passwords_overwrites_hash(db):
    payload = export_payload(db)
    qa = User(
        username="qa02",
        real_name="测试员乙",
        password_hash=hash_password("old-password"),
        status=UserStatus.ACTIVE,
    )
    db.add(qa)
    db.commit()
    payload["users"].append(
        {
            "username": "qa02",
            "password_hash": hash_password(QA_PASSWORD),
            "real_name": "测试员乙",
            "status": "ACTIVE",
        }
    )

    import_payload(db, payload)
    db.commit()
    unchanged = db.scalar(select(User).where(User.username == "qa02"))
    assert verify_password("old-password", unchanged.password_hash)

    import_payload(db, payload, update_passwords=True)
    db.commit()
    changed = db.scalar(select(User).where(User.username == "qa02"))
    assert verify_password(QA_PASSWORD, changed.password_hash)
