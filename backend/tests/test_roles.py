"""角色管理测试（F6.3）。"""

from __future__ import annotations

from app.core.constants import BUILTIN_ROLES

BASE = "/api/v1"


def test_builtin_roles_seeded(client, admin_headers):
    roles = client.get(f"{BASE}/roles", headers=admin_headers).json()
    by_code = {r["code"]: r for r in roles}
    for code, name, _ in BUILTIN_ROLES:
        assert code in by_code
        assert by_code[code]["is_builtin"] is True
        assert by_code[code]["name"] == name


def test_roles_readable_by_any_logged_in_user(client, normal_headers):
    """角色名要用于展示（如流程的发起范围），普通用户可读。"""
    assert client.get(f"{BASE}/roles", headers=normal_headers).status_code == 200
    assert client.get(f"{BASE}/roles").status_code == 401


def test_create_update_delete(client, admin_headers):
    created = client.post(
        f"{BASE}/roles",
        headers=admin_headers,
        json={"code": "auditor", "name": "审计员", "description": "只读审计"},
    )
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["is_builtin"] is False
    assert role["member_count"] == 0

    updated = client.put(
        f"{BASE}/roles/{role['id']}", headers=admin_headers, json={"name": "高级审计员"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "高级审计员"

    assert client.delete(f"{BASE}/roles/{role['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{BASE}/roles/{role['id']}", headers=admin_headers).status_code == 404


def test_duplicate_code_conflicts(client, admin_headers):
    resp = client.post(
        f"{BASE}/roles", headers=admin_headers, json={"code": "auditor", "name": "一"}
    )
    assert resp.status_code == 201
    dup = client.post(
        f"{BASE}/roles", headers=admin_headers, json={"code": "auditor", "name": "二"}
    )
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "ROLE_CODE_EXISTS"


def test_builtin_role_protected(client, admin_headers, designer_role):
    assert client.delete(
        f"{BASE}/roles/{designer_role.id}", headers=admin_headers
    ).json()["detail"]["code"] == "ROLE_BUILTIN_PROTECTED"

    resp = client.put(
        f"{BASE}/roles/{designer_role.id}", headers=admin_headers, json={"name": "改名"}
    )
    # 内置角色可以改显示名（引用的是 code），但不可停用
    assert resp.status_code == 200
    assert resp.json()["name"] == "改名"

    disabled = client.put(
        f"{BASE}/roles/{designer_role.id}", headers=admin_headers, json={"status": "DISABLED"}
    )
    assert disabled.status_code == 409
    assert disabled.json()["detail"]["code"] == "ROLE_BUILTIN_PROTECTED"


def test_cannot_delete_role_with_members(client, admin_headers, designer_role, normal_user):
    assert client.put(
        f"{BASE}/roles/{designer_role.id}/members",
        headers=admin_headers,
        json={"user_ids": [normal_user.id]},
    ).status_code == 200

    resp = client.delete(f"{BASE}/roles/{designer_role.id}", headers=admin_headers)
    # 内置角色先撞上保护规则
    assert resp.json()["detail"]["code"] == "ROLE_BUILTIN_PROTECTED"

    # 换一个自定义角色验证「有成员不可删」
    custom = client.post(
        f"{BASE}/roles", headers=admin_headers, json={"code": "custom", "name": "自定义"}
    ).json()
    client.put(
        f"{BASE}/roles/{custom['id']}/members", headers=admin_headers, json={"user_ids": [normal_user.id]}
    )
    resp = client.delete(f"{BASE}/roles/{custom['id']}", headers=admin_headers)
    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["code"] == "ROLE_HAS_MEMBERS"
    assert body["extra"]["member_count"] == 1


def test_set_members_is_overwrite(client, admin_headers, designer_role, normal_user, db):
    from sqlalchemy import select

    from app.models import User

    admin = db.scalar(select(User).where(User.username == "admin"))
    role_id = designer_role.id

    client.put(
        f"{BASE}/roles/{role_id}/members",
        headers=admin_headers,
        json={"user_ids": [normal_user.id, admin.id]},
    )
    members = client.get(f"{BASE}/roles/{role_id}/members", headers=admin_headers).json()
    assert {m["id"] for m in members} == {normal_user.id, admin.id}
    assert client.get(f"{BASE}/roles/{role_id}", headers=admin_headers).json()["member_count"] == 2

    # 覆盖成只有 admin —— normal_user 的角色应被移除
    client.put(f"{BASE}/roles/{role_id}/members", headers=admin_headers, json={"user_ids": [admin.id]})
    members = client.get(f"{BASE}/roles/{role_id}/members", headers=admin_headers).json()
    assert {m["id"] for m in members} == {admin.id}

    # 重复授予同一人不报错（幂等）
    again = client.put(
        f"{BASE}/roles/{role_id}/members", headers=admin_headers, json={"user_ids": [admin.id, admin.id]}
    )
    assert again.status_code == 200
    assert client.get(f"{BASE}/roles/{role_id}", headers=admin_headers).json()["member_count"] == 1


def test_member_count_reflected_in_list(client, admin_headers, designer_role, normal_user):
    client.put(
        f"{BASE}/roles/{designer_role.id}/members",
        headers=admin_headers,
        json={"user_ids": [normal_user.id]},
    )
    roles = {r["code"]: r for r in client.get(f"{BASE}/roles", headers=admin_headers).json()}
    assert roles["designer"]["member_count"] == 1
    assert roles["finance"]["member_count"] == 0


def test_writes_require_admin(client, normal_headers):
    assert client.post(
        f"{BASE}/roles", headers=normal_headers, json={"code": "hack", "name": "x"}
    ).status_code == 403
    assert client.put(
        f"{BASE}/roles/1", headers=normal_headers, json={"name": "x"}
    ).status_code == 403
    assert client.delete(f"{BASE}/roles/1", headers=normal_headers).status_code == 403


def test_code_pattern_enforced(client, admin_headers):
    # 必须小写字母开头、仅小写字母数字下划线
    resp = client.post(
        f"{BASE}/roles", headers=admin_headers, json={"code": "Bad-Code", "name": "x"}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_assigning_unknown_role_fails(client, admin_headers):
    resp = client.post(
        f"{BASE}/users",
        headers=admin_headers,
        json={
            "username": "withbadrole",
            "password": "pass123456",
            "real_name": "角色不存在",
            "role_ids": [999999],
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ROLE_NOT_FOUND"
