from __future__ import annotations

from typing import Any, Callable

import pytest

from support.client import ApiClient
from support.factories import TEST_PASSWORD, create_user, find_flow, username


def _flatten_depts(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        result.append(node)
        result.extend(_flatten_depts(node.get("children") or []))
    return result


@pytest.fixture(scope="session")
def admin_client() -> ApiClient:
    client, _ = ApiClient.login("admin", "admin123456")
    yield client
    client.close()


@pytest.fixture(scope="session")
def zhangsan_client() -> ApiClient:
    client, _ = ApiClient.login("zhangsan", "demo123456")
    yield client
    client.close()


@pytest.fixture(scope="session")
def lisi_client() -> ApiClient:
    client, _ = ApiClient.login("lisi", "demo123456")
    yield client
    client.close()


@pytest.fixture(scope="session")
def wangwu_client() -> ApiClient:
    client, _ = ApiClient.login("wangwu", "demo123456")
    yield client
    client.close()


@pytest.fixture(scope="session")
def zhaoliu_client() -> ApiClient:
    client, _ = ApiClient.login("zhaoliu", "demo123456")
    yield client
    client.close()


@pytest.fixture(scope="session")
def db_dialect(admin_client: ApiClient) -> str:
    response = admin_client.get("readyz")
    assert response.status_code == 200, response.text
    return response.json()["database"]


@pytest.fixture(scope="session")
def seed(admin_client: ApiClient) -> dict[str, Any]:
    users = admin_client.get("users?size=100").json()["items"]
    roles = admin_client.get("roles?size=100").json()
    depts = _flatten_depts(admin_client.get("departments/tree").json())
    flows = admin_client.get("flow-templates?size=200").json()
    return {
        "users": {user["username"]: user for user in users},
        "roles": {role["code"]: role for role in roles},
        "depts": {dept["code"]: dept for dept in depts},
        "flows": {flow["code"]: flow for flow in flows},
        "leave_flow": find_flow(admin_client, "SAMPLE_LEAVE_FLOW"),
        "reimburse_flow": find_flow(admin_client, "SAMPLE_REIMBURSE_FLOW"),
    }


@pytest.fixture
def make_user(admin_client: ApiClient) -> Callable[..., tuple[ApiClient, dict[str, Any]]]:
    def _make(
        *,
        dept_id: int | None = None,
        role_ids: list[int] | None = None,
        name: str | None = None,
    ) -> tuple[ApiClient, dict[str, Any]]:
        uname = name or username()
        user = create_user(
            admin_client,
            username_value=uname,
            real_name=uname,
            dept_id=dept_id,
            role_ids=role_ids,
        )
        client, _ = ApiClient.login(uname, TEST_PASSWORD)
        return client, user

    return _make


@pytest.fixture
def outsider(admin_client: ApiClient) -> tuple[ApiClient, dict[str, Any]]:
    uname = username("e2e_outsider")
    user = create_user(admin_client, username_value=uname, real_name="E2E 无关用户")
    client, _ = ApiClient.login(uname, TEST_PASSWORD)
    yield client, user
    client.close()
