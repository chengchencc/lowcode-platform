"""应用元信息：公开可读，前端登录页用它渲染系统名称。"""

from __future__ import annotations

from support.client import ApiClient


def test_meta_is_public_and_returns_app_name() -> None:
    anon = ApiClient()
    response = anon.get("meta")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"].strip()
    assert body["version"]
