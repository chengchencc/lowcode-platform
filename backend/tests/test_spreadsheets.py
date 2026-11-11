"""共享电子表格：权限、快照保存与近实时状态。"""

from __future__ import annotations

from tests.conftest import make_user

BASE = "/api/v1"
SHEETS = f"{BASE}/spreadsheet-workbooks"

SNAPSHOT = {
    "id": "wb-1",
    "name": "测试工作簿",
    "sheetOrder": ["s1"],
    "sheets": {"s1": {"id": "s1", "name": "Sheet1", "cellData": {}}},
}


def _create(client, headers, **overrides) -> dict:
    payload = {"name": "部门共享表", "description": "测试", **overrides}
    resp = client.post(SHEETS, headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_list_visibility(client, db, normal_headers, normal_user, admin_headers):
    shared = _create(client, normal_headers, viewer_scope={"all": True})

    listed = client.get(SHEETS, headers=normal_headers).json()
    assert [item["id"] for item in listed] == [shared["id"]]

    other = make_user(db, username="other")
    from tests.conftest import USER_PASSWORD, login_as

    other_headers = login_as(client, other.username, USER_PASSWORD)
    # all=true 时其他人可见但不可编辑
    visible = client.get(SHEETS, headers=other_headers).json()
    assert visible[0]["can_edit"] is False

    # 管理员能看到全部，包括未共享给管理员的
    private = _create(client, normal_headers)
    admin_list = client.get(SHEETS, headers=admin_headers).json()
    assert {item["id"] for item in admin_list} >= {shared["id"], private["id"]}


def test_editor_scope_and_manage_permissions(client, db, normal_headers, normal_user):
    editor = make_user(db, username="editor")
    from tests.conftest import USER_PASSWORD, login_as

    editor_headers = login_as(client, editor.username, USER_PASSWORD)
    workbook = _create(
        client, normal_headers,
        viewer_scope={"all": True},
        editor_scope={"users": [editor.id]},
    )

    assert client.get(SHEETS, headers=editor_headers).json()[0]["can_edit"] is True
    saved = client.post(
        f"{SHEETS}/{workbook['id']}/save",
        headers=editor_headers,
        json={"snapshot": SNAPSHOT, "version": 0},
    )
    assert saved.status_code == 200, saved.text

    # 编辑者不能改共享范围
    denied = client.put(
        f"{SHEETS}/{workbook['id']}", headers=editor_headers, json={"name": "改名"}
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "SPREADSHEET_MANAGE_FORBIDDEN"


def test_save_version_conflict_and_state(client, normal_headers):
    workbook = _create(client, normal_headers)
    first = client.post(
        f"{SHEETS}/{workbook['id']}/save",
        headers=normal_headers,
        json={"snapshot": SNAPSHOT, "version": 0},
    )
    assert first.status_code == 200
    assert first.json()["version"] == 1

    stale = client.post(
        f"{SHEETS}/{workbook['id']}/save",
        headers=normal_headers,
        json={"snapshot": SNAPSHOT, "version": 0},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "SPREADSHEET_VERSION_CONFLICT"

    unchanged = client.get(
        f"{SHEETS}/{workbook['id']}/state",
        headers=normal_headers,
        params={"known_version": 1},
    ).json()
    assert unchanged["changed"] is False
    assert unchanged["snapshot"] is None

    changed = client.get(
        f"{SHEETS}/{workbook['id']}/state",
        headers=normal_headers,
        params={"known_version": 0},
    ).json()
    assert changed["changed"] is True
    assert changed["snapshot"]["id"] == "wb-1"


def test_snapshot_size_limit(client, normal_headers):
    workbook = _create(client, normal_headers)
    huge = {"data": "x" * (5 * 1024 * 1024 + 1)}
    resp = client.post(
        f"{SHEETS}/{workbook['id']}/save",
        headers=normal_headers,
        json={"snapshot": huge, "version": 0},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "SPREADSHEET_TOO_LARGE"


def test_delete_permissions(client, db, normal_headers, normal_user):
    workbook = _create(client, normal_headers)
    other = make_user(db, username="deleter")
    from tests.conftest import USER_PASSWORD, login_as

    other_headers = login_as(client, other.username, USER_PASSWORD)
    denied = client.delete(f"{SHEETS}/{workbook['id']}", headers=other_headers)
    assert denied.status_code == 403

    ok = client.delete(f"{SHEETS}/{workbook['id']}", headers=normal_headers)
    assert ok.status_code == 200
    assert client.get(f"{SHEETS}/{workbook['id']}", headers=normal_headers).status_code == 404


def test_creator_can_always_view_own_workbook(client, normal_headers):
    workbook = _create(client, normal_headers)
    detail = client.get(f"{SHEETS}/{workbook['id']}", headers=normal_headers)
    assert detail.status_code == 200
    assert detail.json()["can_edit"] is True
    assert detail.json()["snapshot"] is None
