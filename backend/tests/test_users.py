"""用户管理测试（F6.1）。"""

from __future__ import annotations

from app.core.constants import UserStatus
from tests.conftest import USER_PASSWORD, login_as, make_user

BASE = "/api/v1"


def _create(client, headers, **overrides) -> dict:
    payload = {
        "username": "newbie",
        "password": "newbie123456",
        "real_name": "新同事",
        **overrides,
    }
    resp = client.post(f"{BASE}/users", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_writes_require_admin(client, normal_headers):
    assert client.get(f"{BASE}/users", headers=normal_headers).status_code == 403
    assert client.post(
        f"{BASE}/users",
        headers=normal_headers,
        json={"username": "x", "password": "xxxxxx", "real_name": "x"},
    ).status_code == 403
    # 缺 token 是 401，不是 403
    assert client.get(f"{BASE}/users").status_code == 401


def test_create_and_read(client, admin_headers, db):
    from sqlalchemy import select

    from app.models import Department

    tech = db.scalar(select(Department).where(Department.code == "TECH"))
    created = _create(client, admin_headers, dept_id=tech.id, position="工程师")

    assert created["username"] == "newbie"
    assert created["dept_name"] == "技术部"  # 列表/详情都要带上部门名，前端不额外查询
    assert created["status"] == UserStatus.ACTIVE
    assert created["roles"] == []
    assert created["last_login_at"] is None

    fetched = client.get(f"{BASE}/users/{created['id']}", headers=admin_headers).json()
    assert fetched["real_name"] == "新同事"


def test_duplicate_username_conflicts(client, admin_headers):
    _create(client, admin_headers, username="dup")
    resp = client.post(
        f"{BASE}/users",
        headers=admin_headers,
        json={"username": "dup", "password": "dup123456", "real_name": "重复"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "USERNAME_EXISTS"


def test_duplicate_email_conflicts(client, admin_headers):
    _create(client, admin_headers, username="e1", email="same@example.com")
    resp = client.post(
        f"{BASE}/users",
        headers=admin_headers,
        json={
            "username": "e2",
            "password": "e2pass123",
            "real_name": "邮箱重复",
            "email": "SAME@example.com",  # 大小写不同也应判定为重复
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "EMAIL_EXISTS"


def test_update_and_role_assignment(client, admin_headers, designer_role):
    created = _create(client, admin_headers, username="designer1")

    resp = client.put(
        f"{BASE}/users/{created['id']}",
        headers=admin_headers,
        json={"real_name": "改过的名字", "role_ids": [designer_role.id]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["real_name"] == "改过的名字"
    assert [r["code"] for r in body["roles"]] == ["designer"]

    # 覆盖式：传空数组即清空角色
    cleared = client.put(
        f"{BASE}/users/{created['id']}", headers=admin_headers, json={"role_ids": []}
    ).json()
    assert cleared["roles"] == []


def test_designer_can_reach_designer_gated_endpoint(client, admin_headers, designer_role):
    """设计者角色是否真的生效 —— 通过登录响应里的 is_designer 验证。"""
    created = _create(client, admin_headers, username="designer2")
    client.put(
        f"{BASE}/users/{created['id']}", headers=admin_headers, json={"role_ids": [designer_role.id]}
    )

    login = client.post(
        f"{BASE}/auth/login", json={"username": "designer2", "password": "newbie123456"}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    me = client.get(f"{BASE}/auth/me", headers=headers).json()
    assert me["is_designer"] is True
    assert me["is_admin"] is False


def test_dept_filter_includes_sub_departments(client, admin_headers, db):
    from sqlalchemy import select

    from app.models import Department

    hq = db.scalar(select(Department).where(Department.code == "HQ"))
    tech = db.scalar(select(Department).where(Department.code == "TECH"))
    _create(client, admin_headers, username="in_tech", dept_id=tech.id)
    _create(client, admin_headers, username="in_hq", dept_id=hq.id)

    # 种子里的 admin 也挂在总公司，所以 HQ 的直属成员是它俩
    direct = client.get(
        f"{BASE}/users", headers=admin_headers, params={"dept_id": hq.id}
    ).json()
    assert {u["username"] for u in direct["items"]} == {"in_hq", "admin"}

    # 勾选「含子部门」后技术部的 in_tech 才会出现
    with_sub = client.get(
        f"{BASE}/users", headers=admin_headers, params={"dept_id": hq.id, "include_sub_depts": True}
    ).json()
    assert {u["username"] for u in with_sub["items"]} == {"in_hq", "in_tech", "admin"}


def test_keyword_search(client, admin_headers):
    _create(client, admin_headers, username="searchme", real_name="搜索我")
    found = client.get(
        f"{BASE}/users", headers=admin_headers, params={"keyword": "搜索"}
    ).json()
    assert [u["username"] for u in found["items"]] == ["searchme"]


def test_pagination(client, admin_headers):
    for i in range(5):
        _create(client, admin_headers, username=f"pg{i}")

    page1 = client.get(
        f"{BASE}/users", headers=admin_headers, params={"page": 1, "size": 2}
    ).json()
    assert len(page1["items"]) == 2
    assert page1["total"] == 6  # 5 个新建 + admin
    page3 = client.get(
        f"{BASE}/users", headers=admin_headers, params={"page": 3, "size": 2}
    ).json()
    assert len(page3["items"]) == 2
    assert {u["id"] for u in page1["items"]} & {u["id"] for u in page3["items"]} == set()


def test_options_available_to_normal_user(client, normal_headers):
    """人员选择器要对所有登录用户开放（发起表单时要用）。"""
    resp = client.get(f"{BASE}/users/options", headers=normal_headers)
    assert resp.status_code == 200, resp.text
    assert {"admin", "zhangsan"} <= {u["username"] for u in resp.json()}


def test_reset_password_invalidates_existing_session(client, admin_headers, normal_headers, normal_user):
    assert client.get(f"{BASE}/auth/me", headers=normal_headers).status_code == 200

    resp = client.post(
        f"{BASE}/users/{normal_user.id}/reset-password",
        headers=admin_headers,
        json={"new_password": "reset-by-admin"},
    )
    assert resp.status_code == 200, resp.text

    stale = client.get(f"{BASE}/auth/me", headers=normal_headers)
    assert stale.status_code == 401
    assert stale.json()["detail"]["code"] == "TOKEN_REVOKED"

    assert client.post(
        f"{BASE}/auth/login", json={"username": normal_user.username, "password": "reset-by-admin"}
    ).status_code == 200


def test_disable_blocks_login_and_kills_session(client, admin_headers, normal_headers, normal_user):
    resp = client.post(
        f"{BASE}/users/{normal_user.id}/status",
        headers=admin_headers,
        json={"status": UserStatus.DISABLED},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == UserStatus.DISABLED

    assert client.get(f"{BASE}/auth/me", headers=normal_headers).status_code == 401
    login = client.post(
        f"{BASE}/auth/login", json={"username": normal_user.username, "password": USER_PASSWORD}
    )
    assert login.status_code == 401
    assert login.json()["detail"]["code"] == "ACCOUNT_DISABLED"


def test_cannot_disable_or_delete_self(client, admin_headers, db):
    from sqlalchemy import select

    from app.models import User

    admin = db.scalar(select(User).where(User.username == "admin"))

    disable = client.post(
        f"{BASE}/users/{admin.id}/status",
        headers=admin_headers,
        json={"status": UserStatus.DISABLED},
    )
    assert disable.status_code == 400
    assert disable.json()["detail"]["code"] == "CANNOT_DISABLE_SELF"

    delete = client.delete(f"{BASE}/users/{admin.id}", headers=admin_headers)
    assert delete.status_code == 400
    assert delete.json()["detail"]["code"] == "CANNOT_DELETE_SELF"


def test_cannot_delete_or_disable_last_superuser(client, db, platform_admin_role):
    """仅剩一名超管时不能再删/停用它，否则系统永久失去管理入口。

    actor 必须是「持有 platform_admin 角色、但 is_superuser=False」的账号：
    用超管自己当 actor 会先被 CANNOT_DELETE_SELF / CANNOT_DISABLE_SELF 拦下，
    根本走不到这条规则。
    """
    from sqlalchemy import select

    from app.models import User

    admin = db.scalar(select(User).where(User.username == "admin"))
    assert admin.is_superuser is True

    deputy = make_user(
        db, username="deputy", password="deputy123456", role=platform_admin_role
    )
    headers = login_as(client, deputy.username, "deputy123456")

    # 确认 deputy 确实有管理权限，但本身不是超管 —— 所以「最后一个超管」是 admin
    me = client.get(f"{BASE}/auth/me", headers=headers).json()
    assert me["is_admin"] is True
    assert me["user"]["is_superuser"] is False

    disable = client.post(
        f"{BASE}/users/{admin.id}/status", headers=headers, json={"status": UserStatus.DISABLED}
    )
    assert disable.status_code == 400
    assert disable.json()["detail"]["code"] == "LAST_SUPERUSER"

    delete = client.delete(f"{BASE}/users/{admin.id}", headers=headers)
    assert delete.status_code == 400
    assert delete.json()["detail"]["code"] == "LAST_SUPERUSER"


def test_last_superuser_guard_lifts_when_a_second_exists(client, db, platform_admin_role):
    """有第二名超管时保护解除 —— 保证上面的 400 不是「永远删不掉任何人」的假象。"""
    from sqlalchemy import select

    from app.models import User

    admin = db.scalar(select(User).where(User.username == "admin"))
    deputy = make_user(db, username="deputy2", password="deputy123456", role=platform_admin_role)
    second = make_user(db, username="super2", password="super2pass", is_superuser=True)
    headers = login_as(client, deputy.username, "deputy123456")

    assert client.delete(f"{BASE}/users/{second.id}", headers=headers).status_code == 200
    # 又只剩 admin 一个超管了，保护恢复
    blocked = client.delete(f"{BASE}/users/{admin.id}", headers=headers)
    assert blocked.status_code == 400
    assert blocked.json()["detail"]["code"] == "LAST_SUPERUSER"


def test_delete_clears_department_manager_reference(client, admin_headers, db):
    """departments.manager_user_id 无外键，删除用户时必须手动清理悬挂引用。"""
    from sqlalchemy import select

    from app.models import Department

    tech = db.scalar(select(Department).where(Department.code == "TECH"))
    created = _create(client, admin_headers, username="mgr")
    client.put(
        f"{BASE}/departments/{tech.id}", headers=admin_headers, json={"manager_user_id": created["id"]}
    )

    assert client.delete(f"{BASE}/users/{created['id']}", headers=admin_headers).status_code == 200
    db.refresh(tech)
    assert tech.manager_user_id is None


def test_import_csv(client, admin_headers):
    csv_body = (
        "username,real_name,email,dept_code,position,roles\n"
        "imp1,导入一,imp1@example.com,TECH,工程师,designer\n"
        "imp2,导入二,,FINANCE,会计,\n"
        "imp3,导入三,,NOPE_DEPT,,\n"      # 部门不存在 → 该行失败
        "admin,重复管理员,,TECH,,\n"       # 用户名已存在 → 该行失败
    )
    resp = client.post(
        f"{BASE}/users/import",
        headers=admin_headers,
        files={"file": ("users.csv", csv_body.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 2
    assert {f["line"] for f in body["failed"]} == {4, 5}

    listed = client.get(f"{BASE}/users", headers=admin_headers, params={"keyword": "导入"}).json()
    assert {u["username"] for u in listed["items"]} == {"imp1", "imp2"}
    imp1 = next(u for u in listed["items"] if u["username"] == "imp1")
    assert [r["code"] for r in imp1["roles"]] == ["designer"]
    assert imp1["dept_name"] == "技术部"


def test_import_rejects_non_utf8(client, admin_headers):
    resp = client.post(
        f"{BASE}/users/import",
        headers=admin_headers,
        files={"file": ("bad.csv", "用户名,姓名\n".encode("gbk"), "text/csv")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CSV_ENCODING"


def test_import_requires_columns(client, admin_headers):
    resp = client.post(
        f"{BASE}/users/import",
        headers=admin_headers,
        files={"file": ("bad.csv", b"foo,bar\n1,2\n", "text/csv")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CSV_MISSING_COLUMNS"


def test_validation_error_shape(client, admin_headers):
    """参数校验失败也要走统一的错误体，前端才能一套逻辑处理。"""
    resp = client.post(
        f"{BASE}/users",
        headers=admin_headers,
        json={"username": "bad name!", "password": "123", "real_name": ""},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    fields = {e["field"] for e in detail["extra"]["errors"]}
    assert "body.username" in fields
    assert "body.password" in fields
    assert "body.real_name" in fields
