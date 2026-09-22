"""认证测试（F6.4）。"""

from __future__ import annotations

from app.core.constants import UserStatus
from tests.conftest import ADMIN_PASSWORD, USER_PASSWORD

BASE = "/api/v1"


def test_login_success(client):
    resp = client.post(
        f"{BASE}/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_at"] > 0
    assert body["user"]["username"] == "admin"
    assert body["user"]["is_superuser"] is True
    assert body["user"]["dept_name"] == "总公司"
    assert [r["code"] for r in body["user"]["roles"]] == ["platform_admin"]


def test_login_wrong_password(client):
    resp = client.post(
        f"{BASE}/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_user_returns_same_code_as_wrong_password(client):
    """不泄露「用户名是否存在」，避免账号枚举。"""
    resp = client.post(
        f"{BASE}/auth/login", json={"username": "nobody", "password": "whatever"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_login_disabled_account(client, db, normal_user):
    normal_user.status = UserStatus.DISABLED
    db.commit()

    resp = client.post(
        f"{BASE}/auth/login", json={"username": normal_user.username, "password": USER_PASSWORD}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "ACCOUNT_DISABLED"


def test_me_requires_token(client):
    assert client.get(f"{BASE}/auth/me").status_code == 401

    resp = client.get(f"{BASE}/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "TOKEN_INVALID"


def test_me_shape(client, admin_headers):
    resp = client.get(f"{BASE}/auth/me", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_admin"] is True
    assert body["is_designer"] is True  # 管理员天然具备设计者能力
    assert body["user"]["username"] == "admin"


def test_change_password_revokes_old_token(client, normal_headers, normal_user):
    """改密后旧 token 必须立即失效（token_version 机制）。"""
    assert client.get(f"{BASE}/auth/me", headers=normal_headers).status_code == 200

    resp = client.post(
        f"{BASE}/auth/change-password",
        headers=normal_headers,
        json={"old_password": USER_PASSWORD, "new_password": "brand-new-pass"},
    )
    assert resp.status_code == 200, resp.text

    stale = client.get(f"{BASE}/auth/me", headers=normal_headers)
    assert stale.status_code == 401
    assert stale.json()["detail"]["code"] == "TOKEN_REVOKED"

    # 新密码可用
    relogin = client.post(
        f"{BASE}/auth/login",
        json={"username": normal_user.username, "password": "brand-new-pass"},
    )
    assert relogin.status_code == 200


def test_change_password_rejects_wrong_old_password(client, normal_headers):
    resp = client.post(
        f"{BASE}/auth/change-password",
        headers=normal_headers,
        json={"old_password": "not-the-password", "new_password": "brand-new-pass"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "OLD_PASSWORD_MISMATCH"


def test_change_password_rejects_same_password(client, normal_headers):
    resp = client.post(
        f"{BASE}/auth/change-password",
        headers=normal_headers,
        json={"old_password": USER_PASSWORD, "new_password": USER_PASSWORD},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "PASSWORD_UNCHANGED"


def test_refresh_issues_working_access_token(client):
    login = client.post(
        f"{BASE}/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}
    ).json()

    resp = client.post(
        f"{BASE}/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert resp.status_code == 200, resp.text
    new_access = resp.json()["access_token"]

    me = client.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


def test_access_token_cannot_be_used_as_refresh_token(client, admin_headers):
    """token 类型必须严格区分，否则 access 泄漏等价于 refresh 泄漏。"""
    access = admin_headers["Authorization"].removeprefix("Bearer ")
    resp = client.post(f"{BASE}/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "TOKEN_TYPE_MISMATCH"


def test_logout_revokes_token(client, normal_headers):
    assert client.post(f"{BASE}/auth/logout", headers=normal_headers).status_code == 200

    resp = client.get(f"{BASE}/auth/me", headers=normal_headers)
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "TOKEN_REVOKED"


def test_refresh_rejected_after_logout(client):
    login = client.post(
        f"{BASE}/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    client.post(f"{BASE}/auth/logout", headers=headers)

    resp = client.post(
        f"{BASE}/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "TOKEN_REVOKED"
