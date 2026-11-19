from __future__ import annotations

from support.client import ApiClient, refresh
from support.factories import TEST_PASSWORD, create_user, username


def test_login_and_me(admin_client: ApiClient, zhangsan_client: ApiClient) -> None:
    admin_me = admin_client.get("auth/me")
    assert admin_me.status_code == 200, admin_me.text
    admin_body = admin_me.json()
    assert admin_body["user"]["username"] == "admin"
    assert admin_body["is_admin"] is True

    zhang_me = zhangsan_client.get("auth/me")
    assert zhang_me.status_code == 200, zhang_me.text
    zhang_body = zhang_me.json()
    assert zhang_body["user"]["username"] == "zhangsan"
    assert zhang_body["is_admin"] is False
    assert zhang_body["is_designer"] is False


def test_wrong_password_does_not_leak_account_existence() -> None:
    anon = ApiClient()
    wrong = anon.post("auth/login", json={"username": "zhangsan", "password": "wrong-password"})
    missing = anon.post(
        "auth/login", json={"username": "no-such-user-e2e", "password": "wrong-password"}
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    assert missing.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    assert wrong.json()["detail"]["message"] == missing.json()["detail"]["message"]
    assert "token" not in wrong.text.lower()


def test_missing_token_is_rejected() -> None:
    anon = ApiClient()
    response = anon.get("auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "NOT_AUTHENTICATED"


def test_logout_invalidates_access_and_refresh_tokens(admin_client: ApiClient) -> None:
    uname = username("e2e_logout")
    create_user(admin_client, username_value=uname, real_name="Logout E2E")
    client, login_body = ApiClient.login(uname, TEST_PASSWORD)
    try:
        assert client.get("auth/me").status_code == 200
        assert client.post("auth/logout").status_code == 200

        me = client.get("auth/me")
        assert me.status_code == 401
        assert me.json()["detail"]["code"] in {"TOKEN_REVOKED", "TOKEN_INVALID"}

        refreshed = refresh(login_body["refresh_token"])
        assert refreshed.status_code in (401, 403)
    finally:
        client.close()


def test_change_password_invalidates_old_tokens(admin_client: ApiClient) -> None:
    uname = username("e2e_chpwd")
    create_user(admin_client, username_value=uname, real_name="Change Password E2E")
    client, _ = ApiClient.login(uname, TEST_PASSWORD)
    try:
        changed = client.post(
            "auth/change-password",
            json={"old_password": TEST_PASSWORD, "new_password": "newPass123"},
        )
        assert changed.status_code == 200, changed.text
        assert client.get("auth/me").status_code == 401

        old_login = ApiClient().post(
            "auth/login", json={"username": uname, "password": TEST_PASSWORD}
        )
        assert old_login.status_code == 401
        new_login = ApiClient().post(
            "auth/login", json={"username": uname, "password": "newPass123"}
        )
        assert new_login.status_code == 200
    finally:
        client.close()


def test_disable_user_invalidates_tokens_and_blocks_login(admin_client: ApiClient) -> None:
    uname = username("e2e_disabled")
    user = create_user(admin_client, username_value=uname, real_name="Disabled E2E")
    client, _ = ApiClient.login(uname, TEST_PASSWORD)
    try:
        disabled = admin_client.post(
            f"users/{user['id']}/status", json={"status": "DISABLED"}
        )
        assert disabled.status_code == 200, disabled.text
        assert client.get("auth/me").status_code == 401
        blocked = ApiClient().post(
            "auth/login", json={"username": uname, "password": TEST_PASSWORD}
        )
        assert blocked.status_code in (401, 403)

        enabled = admin_client.post(
            f"users/{user['id']}/status", json={"status": "ACTIVE"}
        )
        assert enabled.status_code == 200, enabled.text
        again = ApiClient().post(
            "auth/login", json={"username": uname, "password": TEST_PASSWORD}
        )
        assert again.status_code == 200
    finally:
        client.close()


def test_admin_reset_password_invalidates_old_token(admin_client: ApiClient) -> None:
    uname = username("e2e_reset")
    user = create_user(admin_client, username_value=uname, real_name="Reset E2E")
    client, _ = ApiClient.login(uname, TEST_PASSWORD)
    try:
        reset = admin_client.post(
            f"users/{user['id']}/reset-password",
            json={"new_password": "resetPass123"},
        )
        assert reset.status_code == 200, reset.text
        assert client.get("auth/me").status_code == 401
        assert ApiClient().post(
            "auth/login", json={"username": uname, "password": TEST_PASSWORD}
        ).status_code == 401
        assert ApiClient().post(
            "auth/login", json={"username": uname, "password": "resetPass123"}
        ).status_code == 200
    finally:
        client.close()
