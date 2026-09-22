"""操作审计查询测试（F6.6）。

这个端点是端到端冒烟时才暴露出来的问题（AuditLogOut 缺 from_attributes，
ORM 行过不了校验 → 500）。补上用例，避免回归。
"""

from __future__ import annotations

BASE = "/api/v1"


def test_audit_logs_returns_orm_rows(client, admin_headers):
    """先制造几条审计，再读回来 —— 覆盖「ORM 对象直接序列化」这条路径。"""
    client.post(
        f"{BASE}/departments", headers=admin_headers, json={"name": "审计部", "code": "AUDIT"}
    )

    resp = client.get(f"{BASE}/admin/audit-logs", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] >= 1
    assert {"items", "total", "page", "size"} <= set(body)
    first = body["items"][0]
    # 字段齐全，且时间被正确序列化为 ISO 字符串
    assert set(first) >= {
        "id",
        "actor_id",
        "actor_name",
        "biz_type",
        "biz_id",
        "action",
        "summary",
        "detail",
        "ip",
        "created_at",
    }
    assert isinstance(first["created_at"], str)


def test_audit_records_all_org_writes(client, admin_headers):
    dept = client.post(
        f"{BASE}/departments", headers=admin_headers, json={"name": "留痕部", "code": "TRACE"}
    ).json()
    client.post(
        f"{BASE}/roles", headers=admin_headers, json={"code": "trace_role", "name": "留痕角色"}
    )
    user = client.post(
        f"{BASE}/users",
        headers=admin_headers,
        json={
            "username": "traced",
            "password": "traced12345",
            "real_name": "被留痕",
            "dept_id": dept["id"],
        },
    ).json()
    client.post(
        f"{BASE}/users/{user['id']}/status",
        headers=admin_headers,
        json={"status": "DISABLED"},
    )

    logs = client.get(
        f"{BASE}/admin/audit-logs", headers=admin_headers, params={"size": 100}
    ).json()["items"]
    pairs = {(x["biz_type"], x["action"]) for x in logs}

    assert ("DEPT", "CREATE") in pairs
    assert ("ROLE", "CREATE") in pairs
    assert ("USER", "CREATE") in pairs
    assert ("USER", "DISABLE") in pairs

    # 操作人冗余快照要落上，且摘要可读
    dept_log = next(x for x in logs if x["biz_type"] == "DEPT")
    assert dept_log["actor_name"] == "平台管理员"
    assert "留痕部" in dept_log["summary"]


def test_audit_filter_by_biz_type(client, admin_headers):
    client.post(
        f"{BASE}/departments", headers=admin_headers, json={"name": "筛选部", "code": "FILTER"}
    )

    resp = client.get(
        f"{BASE}/admin/audit-logs", headers=admin_headers, params={"biz_type": "DEPT"}
    )
    assert resp.status_code == 200, resp.text
    assert all(x["biz_type"] == "DEPT" for x in resp.json()["items"])


def test_audit_requires_admin(client, normal_headers):
    assert client.get(f"{BASE}/admin/audit-logs", headers=normal_headers).status_code == 403
    assert client.get(f"{BASE}/admin/audit-logs").status_code == 401


def test_audit_is_append_only(client, db, admin_headers):
    """审计记录不该有 updated_at —— 只增不改（PRD §7）。"""
    from app.models import AuditLog

    assert not hasattr(AuditLog, "updated_at")
