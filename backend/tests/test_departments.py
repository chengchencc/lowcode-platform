"""部门管理测试（F6.2）。物化路径的正确性是后续「部门主管」审批人解析的地基。"""

from __future__ import annotations

from sqlalchemy import select

from app.models import Department

BASE = "/api/v1"


def _tree(client, headers) -> list[dict]:
    resp = client.get(f"{BASE}/departments/tree", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_tree_from_seed(client, admin_headers):
    tree = _tree(client, admin_headers)
    assert len(tree) == 1
    hq = tree[0]
    assert hq["name"] == "总公司"
    assert hq["path"] == f"/{hq['id']}/"
    assert hq["level"] == 1

    child_names = {c["name"] for c in hq["children"]}
    assert {"技术部", "产品部", "财务部", "人力资源部"} <= child_names
    for child in hq["children"]:
        assert child["level"] == 2
        assert child["path"].startswith(hq["path"]) and child["path"].endswith(f"{child['id']}/")


def test_create_child_computes_path_and_level(client, admin_headers):
    parent = _tree(client, admin_headers)[0]["children"][0]

    resp = client.post(
        f"{BASE}/departments",
        headers=admin_headers,
        json={"name": "前端组", "code": "FE", "parent_id": parent["id"]},
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["path"] == f"{parent['path']}{created['id']}/"
    assert created["level"] == parent["level"] + 1


def test_duplicate_code_conflicts(client, admin_headers):
    resp = client.post(
        f"{BASE}/departments", headers=admin_headers, json={"name": "重复", "code": "HQ"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "DEPT_CODE_EXISTS"


def test_move_recomputes_descendant_paths(client, db, admin_headers):
    """把一棵子树挂到别处，整棵子树的 path / level 都要跟着平移。

    初始：总公司(1) → 技术部(2)、产品部(2)；技术部 → 前端组(3)
    把技术部挂到产品部下：技术部降到 3，前端组跟着降到 4（整棵子树偏移 +1）。
    """
    hq = db.scalar(select(Department).where(Department.code == "HQ"))
    tech = db.scalar(select(Department).where(Department.code == "TECH"))
    product = db.scalar(select(Department).where(Department.code == "PRODUCT"))
    fe = client.post(
        f"{BASE}/departments",
        headers=admin_headers,
        json={"name": "前端组", "code": "FE", "parent_id": tech.id},
    ).json()
    assert (tech.level, fe["level"]) == (2, 3)
    old_fe_path = fe["path"]

    resp = client.put(
        f"{BASE}/departments/{tech.id}", headers=admin_headers, json={"parent_id": product.id}
    )
    assert resp.status_code == 200, resp.text
    moved = resp.json()
    assert moved["level"] == 3
    assert moved["path"] == f"/{hq.id}/{product.id}/{tech.id}/"

    # 子节点路径整体平移、层级同步偏移
    child = client.get(f"{BASE}/departments/{fe['id']}", headers=admin_headers).json()
    assert child["level"] == 4
    assert child["path"] == f"/{hq.id}/{product.id}/{tech.id}/{fe['id']}/"
    assert child["path"] != old_fe_path

    # 移动后再删除父级的保护仍然成立：产品部现在有子部门，删不掉
    blocked = client.delete(f"{BASE}/departments/{product.id}", headers=admin_headers)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "DEPT_HAS_CHILDREN"


def test_cannot_move_into_own_descendant(client, db, admin_headers):
    hq = db.scalar(select(Department).where(Department.code == "HQ"))
    tech = db.scalar(select(Department).where(Department.code == "TECH"))

    resp = client.put(
        f"{BASE}/departments/{hq.id}", headers=admin_headers, json={"parent_id": tech.id}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "DEPT_PARENT_CYCLE"


def test_cannot_be_own_parent(client, db, admin_headers):
    tech = db.scalar(select(Department).where(Department.code == "TECH"))
    resp = client.put(
        f"{BASE}/departments/{tech.id}", headers=admin_headers, json={"parent_id": tech.id}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "DEPT_PARENT_SELF"


def test_delete_with_children_conflicts(client, db, admin_headers):
    hq = db.scalar(select(Department).where(Department.code == "HQ"))
    resp = client.delete(f"{BASE}/departments/{hq.id}", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "DEPT_HAS_CHILDREN"


def test_delete_with_members_conflicts(client, db, admin_headers):
    hr = db.scalar(select(Department).where(Department.code == "HR"))
    # admin 种子用户挂在总公司；这里把张三放进 HR 再尝试删除
    user_id = client.post(
        f"{BASE}/users",
        headers=admin_headers,
        json={
            "username": "lisi",
            "password": "lisi123456",
            "real_name": "李四",
            "dept_id": hr.id,
        },
    ).json()["id"]
    assert user_id

    resp = client.delete(f"{BASE}/departments/{hr.id}", headers=admin_headers)
    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["code"] == "DEPT_HAS_MEMBERS"
    assert body["extra"]["member_count"] == 1


def test_delete_empty_department(client, db, admin_headers):
    created = client.post(
        f"{BASE}/departments", headers=admin_headers, json={"name": "临时组", "code": "TMP"}
    ).json()
    assert client.delete(f"{BASE}/departments/{created['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"{BASE}/departments/{created['id']}", headers=admin_headers).status_code == 404


def test_set_members_moves_both_directions(client, db, admin_headers):
    tech = db.scalar(select(Department).where(Department.code == "TECH"))
    finance = db.scalar(select(Department).where(Department.code == "FINANCE"))
    a = client.post(
        f"{BASE}/users",
        headers=admin_headers,
        json={"username": "a1", "password": "a1pass123", "real_name": "甲"},
    ).json()["id"]
    b = client.post(
        f"{BASE}/users",
        headers=admin_headers,
        json={"username": "b1", "password": "b1pass123", "real_name": "乙"},
    ).json()["id"]

    # 先都放进技术部
    assert client.put(
        f"{BASE}/departments/{tech.id}/members", headers=admin_headers, json={"user_ids": [a, b]}
    ).status_code == 200
    members = client.get(f"{BASE}/departments/{tech.id}/members", headers=admin_headers).json()
    assert {m["id"] for m in members} == {a, b}

    # 再把 b 挪去财务部；技术部只剩 a
    assert client.put(
        f"{BASE}/departments/{finance.id}/members", headers=admin_headers, json={"user_ids": [b]}
    ).status_code == 200
    assert {m["id"] for m in client.get(f"{BASE}/departments/{tech.id}/members", headers=admin_headers).json()} == {a}
    assert {m["id"] for m in client.get(f"{BASE}/departments/{finance.id}/members", headers=admin_headers).json()} == {b}

    # 清空技术部
    assert client.put(
        f"{BASE}/departments/{tech.id}/members", headers=admin_headers, json={"user_ids": []}
    ).status_code == 200
    assert client.get(f"{BASE}/departments/{tech.id}/members", headers=admin_headers).json() == []


def test_set_members_rejects_unknown_user(client, db, admin_headers):
    tech = db.scalar(select(Department).where(Department.code == "TECH"))
    resp = client.put(
        f"{BASE}/departments/{tech.id}/members", headers=admin_headers, json={"user_ids": [999999]}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "USER_NOT_FOUND"


def test_manager_must_be_active_user(client, db, admin_headers):
    tech = db.scalar(select(Department).where(Department.code == "TECH"))
    resp = client.put(
        f"{BASE}/departments/{tech.id}", headers=admin_headers, json={"manager_user_id": 999999}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "MANAGER_NOT_FOUND"


def test_writes_require_admin(client, normal_headers, db):
    tech = db.scalar(select(Department).where(Department.code == "TECH"))
    assert client.post(
        f"{BASE}/departments", headers=normal_headers, json={"name": "x", "code": "X"}
    ).status_code == 403
    assert client.put(
        f"{BASE}/departments/{tech.id}", headers=normal_headers, json={"name": "y"}
    ).status_code == 403
    assert client.delete(f"{BASE}/departments/{tech.id}", headers=normal_headers).status_code == 403
    # 读接口对登录用户开放
    assert client.get(f"{BASE}/departments/tree", headers=normal_headers).status_code == 200
