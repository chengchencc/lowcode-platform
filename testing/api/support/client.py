"""HTTP 黑盒客户端。

只通过 HTTP 调用运行中的后端，不 import `backend.app` 的任何业务模块。
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")


class ApiClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self._client = httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def _url(self, path: str) -> str:
        return f"{API_BASE_URL}/{path.lstrip('/')}"

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        merged = {"X-Request-Id": uuid.uuid4().hex}
        if self.token:
            merged["Authorization"] = f"Bearer {self.token}"
        if headers:
            merged.update(headers)
        return self._client.request(method, self._url(path), headers=merged, **kwargs)

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)

    @classmethod
    def login(cls, username: str, password: str) -> tuple[ApiClient, dict[str, Any]]:
        client = cls()
        response = client.post("auth/login", json={"username": username, "password": password})
        if response.status_code != 200:
            raise AssertionError(
                f"API 登录失败（{username}）：{response.status_code} {response.text}"
            )
        body = response.json()
        client.token = body["access_token"]
        return client, body


def refresh(refresh_token: str) -> httpx.Response:
    return httpx.post(
        f"{API_BASE_URL}/auth/refresh",
        json={"refresh_token": refresh_token},
        timeout=10.0,
    )
