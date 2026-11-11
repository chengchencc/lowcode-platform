"""工作量统计：协作表格（M12）。"""

from __future__ import annotations

import io

from openpyxl import Workbook, load_workbook

from tests.conftest import USER_PASSWORD, login_as, make_user

BASE = "/api/v1"
SHEET = f"{BASE}/work-stat-sheets"

COLUMNS = [
    {"key": "c_name", "label": "姓名", "type": "text", "required": True},
    {"key": "c_hours", "label": "工时", "type": "number"},
    {"key": "c_date", "label": "日期", "type": "date"},
]


def _create_sheet(client, headers, **overrides) -> dict:
    payload = {
        "name": "部门月度工作量",
        "description": "测试用",
        "columns": COLUMNS,
        **overrides,
    }
    resp = client.post(SHEET, headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_row(client, headers, sheet_id: int, cells: dict) -> dict:
    resp = client.post(f"{SHEET}/{sheet_id}/rows", headers=headers, json={"cells": cells})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_admin_crud_and_visibility(client, admin_headers, normal_headers):
    sheet = _create_sheet(client, admin_headers)
    assert sheet["can_edit"] is True
    assert sheet["columns"][0]["label"] == "姓名"

    visible = client.get(SHEET, headers=normal_headers).json()
    assert [item["id"] for item in visible] == [sheet["id"]]
    assert visible[0]["can_edit"] is False

    updated = client.put(
        f"{SHEET}/{sheet['id']}",
        headers=admin_headers,
        json={"name": "改名后的统计表", "status": "DISABLED"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "改名后的统计表"

    # 停用后普通用户看不到，管理员仍能读
    assert client.get(SHEET, headers=normal_headers).json() == []
    assert client.get(f"{SHEET}/{sheet['id']}", headers=admin_headers).status_code == 200

    assert client.delete(f"{SHEET}/{sheet['id']}", headers=admin_headers).status_code == 200


def test_editor_scope_limits_edit(client, db, admin_headers, normal_headers, normal_user):
    sheet = _create_sheet(
        client,
        admin_headers,
        editor_scope={"roles": [], "depts": [], "users": [normal_user.id]},
    )
    row = _create_row(client, normal_headers, sheet["id"], {"c_name": "张三", "c_hours": 8})
    assert row["cells"]["c_name"] == "张三"

    other = make_user(db, username="lisi", real_name="李四")
    other_headers = login_as(client, other.username, USER_PASSWORD)
    resp = client.post(
        f"{SHEET}/{sheet['id']}/rows",
        headers=other_headers,
        json={"cells": {"c_name": "李四"}},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "WORK_STAT_EDIT_FORBIDDEN"


def test_row_optimistic_lock_and_logs(client, admin_headers):
    sheet = _create_sheet(client, admin_headers)
    row = _create_row(client, admin_headers, sheet["id"], {"c_name": "张三", "c_hours": 8})

    first = client.put(
        f"{SHEET}/{sheet['id']}/rows/{row['id']}",
        headers=admin_headers,
        json={"cells": {"c_name": "张三", "c_hours": 12}, "version": row["version"]},
    )
    assert first.status_code == 200, first.text
    assert first.json()["version"] == row["version"] + 1
    assert first.json()["cells"]["c_hours"] == 12

    stale = client.put(
        f"{SHEET}/{sheet['id']}/rows/{row['id']}",
        headers=admin_headers,
        json={"cells": {"c_name": "张三", "c_hours": 16}, "version": row["version"]},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "WORK_STAT_ROW_CONFLICT"

    logs = client.get(
        f"{SHEET}/{sheet['id']}/rows/{row['id']}/logs", headers=admin_headers
    ).json()
    assert [item["action"] for item in logs] == ["UPDATE", "CREATE"]
    assert logs[0]["before"]["c_hours"] == 8
    assert logs[0]["after"]["c_hours"] == 12


def test_row_validation(client, admin_headers):
    sheet = _create_sheet(client, admin_headers)

    missing = client.post(
        f"{SHEET}/{sheet['id']}/rows", headers=admin_headers, json={"cells": {"c_hours": 1}}
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "WORK_STAT_REQUIRED"

    bad_number = client.post(
        f"{SHEET}/{sheet['id']}/rows",
        headers=admin_headers,
        json={"cells": {"c_name": "张三", "c_hours": "很多"}},
    )
    assert bad_number.status_code == 422
    assert bad_number.json()["detail"]["code"] == "WORK_STAT_INVALID_NUMBER"


def test_import_preview_and_commit(client, admin_headers):
    sheet = _create_sheet(client, admin_headers)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["姓名", "工时", "日期", "备注"])
    worksheet.append(["张三", 8, "2026-11-01", "忽略我"])
    worksheet.append(["李四", 6.5, "2026-11-02", ""])
    buffer = io.BytesIO()
    workbook.save(buffer)
    content = buffer.getvalue()

    preview = client.post(
        f"{SHEET}/{sheet['id']}/import",
        headers=admin_headers,
        params={"dry_run": "true"},
        files={"file": ("work.xlsx", content,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["total_rows"] == 2
    assert body["preview_rows"][0]["c_name"] == "张三"
    assert any("备注" in warning for warning in body["warnings"])

    committed = client.post(
        f"{SHEET}/{sheet['id']}/import",
        headers=admin_headers,
        files={"file": ("work.xlsx", content,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["imported"] == 2

    rows = client.get(f"{SHEET}/{sheet['id']}/rows", headers=admin_headers).json()
    assert [row["cells"]["c_name"] for row in rows] == ["张三", "李四"]

    exported = client.get(f"{SHEET}/{sheet['id']}/export", headers=admin_headers)
    assert exported.status_code == 200
    parsed = load_workbook(io.BytesIO(exported.content), read_only=True)
    values = list(parsed.active.iter_rows(min_row=2, values_only=True))
    assert values[0][0] == "张三"


def test_disabled_sheet_cannot_be_read_by_normal_user(
    client, db, admin_headers, normal_headers
):
    sheet = _create_sheet(client, admin_headers)
    client.put(
        f"{SHEET}/{sheet['id']}", headers=admin_headers, json={"status": "DISABLED"}
    )

    resp = client.get(f"{SHEET}/{sheet['id']}", headers=normal_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "WORK_STAT_SHEET_NOT_FOUND"
