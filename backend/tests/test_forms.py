"""表单模板与版本测试（F1.1–F1.8）。"""

from __future__ import annotations

BASE = "/api/v1"


def _make_template(client, headers, **overrides) -> dict:
    payload = {"name": "报销单", "code": "REIMBURSE", **overrides}
    resp = client.post(f"{BASE}/form-templates", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


REIMBURSE_SCHEMA = {
    "sections": [
        {
            "key": "sec_apply",
            "title": "申请信息",
            "stage": "apply",
            "fields": [
                {"key": "reason", "label": "事由", "type": "textarea", "required": True},
                {"key": "qty", "label": "数量", "type": "number"},
                {"key": "price", "label": "单价", "type": "number"},
                {
                    "key": "items",
                    "label": "费用明细",
                    "type": "subtable",
                    "columns": [
                        {"key": "name", "label": "费用项", "type": "text"},
                        {"key": "qty", "label": "数量", "type": "number"},
                        {"key": "price", "label": "单价", "type": "number"},
                        {
                            "key": "subtotal",
                            "label": "小计",
                            "type": "formula",
                            "formula": {"type": "arithmetic", "expression": "qty * price"},
                        },
                    ],
                },
                {
                    "key": "total",
                    "label": "合计",
                    "type": "formula",
                    "formula": {
                        "type": "subtable_sum",
                        "subtable_key": "items",
                        "column_key": "subtotal",
                    },
                },
            ],
        },
        {
            "key": "sec_supplement",
            "title": "财务补充核销",
            "stage": "supplement",
            "fields": [
                {
                    "key": "actualAmount",
                    "label": "实际核销金额",
                    "type": "number",
                    "visible_at_start": False,
                },
            ],
        },
    ]
}


# --------------------------------------------------------------------------- 权限


def test_form_endpoints_require_designer(client, normal_headers):
    assert client.get(f"{BASE}/form-templates", headers=normal_headers).status_code == 403
    assert client.post(
        f"{BASE}/form-templates", headers=normal_headers, json={"name": "x"}
    ).status_code == 403
    assert client.get(f"{BASE}/form-templates").status_code == 401


def test_designer_can_manage_forms(client, designer_headers):
    assert client.get(f"{BASE}/form-templates", headers=designer_headers).status_code == 200


def test_admin_counts_as_designer(client, admin_headers):
    assert client.get(f"{BASE}/form-templates", headers=admin_headers).status_code == 200


# --------------------------------------------------------------------------- 模板


def test_create_template_bootstraps_draft_version(client, designer_headers):
    template = _make_template(client, designer_headers)
    assert template["status"] == "DRAFT"
    assert template["current_version_id"] is None       # 还没有发布版本
    assert template["draft_version_id"] is not None     # 但有一个可编辑草稿
    assert template["version_count"] == 1

    versions = client.get(
        f"{BASE}/form-templates/{template['id']}/versions", headers=designer_headers
    ).json()
    assert len(versions) == 1
    assert versions[0]["version_no"] == 1
    assert versions[0]["status"] == "DRAFT"


def test_duplicate_code_conflicts(client, designer_headers):
    _make_template(client, designer_headers)
    resp = client.post(
        f"{BASE}/form-templates", headers=designer_headers, json={"name": "另一个", "code": "REIMBURSE"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "FORM_CODE_EXISTS"


def test_list_filters(client, designer_headers):
    """筛选按条件收窄。

    断言用「包含」而不是「恰好等于」：首启会写入**示例流程库**（M6），
    关键词「请假」会同时命中示例里的「请假申请单」，
    分组里也会多出「示例流程库」—— 全等断言依赖「库里只有本用例的数据」。
    """
    _make_template(client, designer_headers, name="报销单", code="A1", group_name="财务")
    _make_template(client, designer_headers, name="请假单", code="A2", group_name="人事")

    by_group = client.get(
        f"{BASE}/form-templates", headers=designer_headers, params={"group_name": "财务"}
    ).json()
    assert [t["name"] for t in by_group] == ["报销单"]

    by_keyword = client.get(
        f"{BASE}/form-templates", headers=designer_headers, params={"keyword": "请假"}
    ).json()
    names = [t["name"] for t in by_keyword]
    assert "请假单" in names
    assert all("请假" in n for n in names)

    groups = client.get(f"{BASE}/form-templates/groups", headers=designer_headers).json()
    assert {"人事", "财务"} <= set(groups)


def test_update_template_metadata(client, designer_headers):
    template = _make_template(client, designer_headers)
    resp = client.put(
        f"{BASE}/form-templates/{template['id']}",
        headers=designer_headers,
        json={"name": "改过的名字", "group_name": "财务", "description": "说明"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "改过的名字"
    assert resp.json()["group_name"] == "财务"


def test_copy_template(client, designer_headers):
    source = _make_template(client, designer_headers)
    resp = client.post(
        f"{BASE}/form-templates/{source['id']}/copy",
        headers=designer_headers,
        json={"name": "报销单副本", "code": "REIMBURSE_COPY"},
    )
    assert resp.status_code == 201, resp.text
    copy = resp.json()
    assert copy["id"] != source["id"]
    assert copy["status"] == "DRAFT"

    # 副本应携带源模板的 schema
    version = client.get(
        f"{BASE}/form-versions/{copy['draft_version_id']}", headers=designer_headers
    ).json()
    assert [s["key"] for s in version["schema_data"]["sections"]] == ["sec_apply"]


def test_delete_template_removes_versions(client, designer_headers):
    template = _make_template(client, designer_headers)
    version_id = template["draft_version_id"]

    assert client.delete(
        f"{BASE}/form-templates/{template['id']}", headers=designer_headers
    ).status_code == 200

    assert client.get(
        f"{BASE}/form-templates/{template['id']}", headers=designer_headers
    ).status_code == 404
    # 版本随模板级联删除
    assert client.get(
        f"{BASE}/form-versions/{version_id}", headers=designer_headers
    ).status_code == 404


# --------------------------------------------------------------------------- 版本生命周期


def test_save_draft_schema(client, designer_headers):
    template = _make_template(client, designer_headers)
    resp = client.put(
        f"{BASE}/form-versions/{template['draft_version_id']}",
        headers=designer_headers,
        json={"schema_data": REIMBURSE_SCHEMA},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["schema_data"]["sections"][0]["key"] == "sec_apply"

    # 列表页的字段数应反映出来
    listed = client.get(f"{BASE}/form-templates", headers=designer_headers).json()
    assert listed[0]["field_count"] == 0  # 尚未发布，没有 current_version


def test_save_allows_work_in_progress_schema(client, designer_headers):
    """保存阶段不做语义校验。

    设计器每次改动都会自动保存，如果这里就卡「单选还没配选项」「公式引用了
    还没建的字段」，设计器根本没法用。这些留到发布时拦
    （见 test_publish_blocked_by_validation）。
    """
    template = _make_template(client, designer_headers)
    unfinished = {
        "sections": [
            {
                "key": "sec1",
                "title": "未完成的表单",
                "fields": [
                    {"key": "bad-key", "label": "标识还不合法", "type": "text"},
                    {"key": "choice", "label": "单选还没配选项", "type": "radio"},
                    {
                        "key": "calc",
                        "label": "公式引用了还没建的字段",
                        "type": "formula",
                        "formula": {"type": "arithmetic", "expression": "notYet * 2"},
                    },
                ],
            }
        ]
    }
    resp = client.put(
        f"{BASE}/form-versions/{template['draft_version_id']}",
        headers=designer_headers,
        json={"schema_data": unfinished},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["schema_data"]["sections"][0]["fields"]) == 3

    # 校验接口会如实报出这些问题（设计器用它做实时提示）
    result = client.post(
        f"{BASE}/form-versions/{template['draft_version_id']}/validate",
        headers=designer_headers,
    ).json()
    assert result["valid"] is False
    codes = {e["code"] for e in result["errors"]}
    assert {"INVALID_KEY", "OPTIONS_REQUIRED", "FORMULA_UNKNOWN_FIELD"} <= codes


def test_save_rejects_malformed_shape(client, designer_headers):
    """形状错误（不是语义错误）仍要在保存时挡下 —— 这类数据存进去没法渲染。"""
    template = _make_template(client, designer_headers)
    resp = client.put(
        f"{BASE}/form-versions/{template['draft_version_id']}",
        headers=designer_headers,
        json={"schema_data": {"sections": [{"title": "缺少 key", "fields": []}]}},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_save_rejects_unknown_control_type(client, designer_headers):
    template = _make_template(client, designer_headers)
    resp = client.put(
        f"{BASE}/form-versions/{template['draft_version_id']}",
        headers=designer_headers,
        json={
            "schema_data": {
                "sections": [
                    {
                        "key": "s",
                        "title": "A",
                        "fields": [{"key": "a", "label": "A", "type": "rich-text-editor"}],
                    }
                ]
            }
        },
    )
    assert resp.status_code == 422


def test_publish_flow_and_archive_previous(client, designer_headers):
    template = _make_template(client, designer_headers)
    v1 = template["draft_version_id"]

    client.put(
        f"{BASE}/form-versions/{v1}",
        headers=designer_headers,
        json={"schema_data": REIMBURSE_SCHEMA},
    )
    published = client.post(
        f"{BASE}/form-versions/{v1}/publish", headers=designer_headers, json={}
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "PUBLISHED"
    assert published.json()["published_at"] is not None

    # 模板从 DRAFT 变成 PUBLISHED，current_version 指向 v1
    after = client.get(f"{BASE}/form-templates/{template['id']}", headers=designer_headers).json()
    assert after["status"] == "PUBLISHED"
    assert after["current_version_id"] == v1
    assert after["current_version_no"] == 1
    # 字段数 = 所有分区的顶层字段 + 子表的列
    #   sec_apply: reason/qty/price/items(子表)/total = 5，items 的 4 列
    #   sec_supplement: actualAmount = 1
    assert after["field_count"] == 5 + 4 + 1

    # 已发布版本不能再改
    blocked = client.put(
        f"{BASE}/form-versions/{v1}",
        headers=designer_headers,
        json={"schema_data": REIMBURSE_SCHEMA},
    )
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["code"] == "VERSION_NOT_EDITABLE"

    # 已发布版本不能删
    assert client.delete(
        f"{BASE}/form-versions/{v1}", headers=designer_headers
    ).json()["detail"]["code"] == "VERSION_NOT_DELETABLE"

    # 新建版本 → 从已发布版本 fork → 发布 → v1 归档
    v2 = client.post(
        f"{BASE}/form-templates/{template['id']}/versions",
        headers=designer_headers,
        json={},
    ).json()
    assert v2["version_no"] == 2
    assert v2["status"] == "DRAFT"
    assert v2["schema_data"]["sections"][0]["key"] == "sec_apply"  # 承袭了 v1 的内容

    client.post(f"{BASE}/form-versions/{v2['id']}/publish", headers=designer_headers, json={})

    versions = {
        v["id"]: v["status"]
        for v in client.get(
            f"{BASE}/form-templates/{template['id']}/versions", headers=designer_headers
        ).json()
    }
    assert versions[v1] == "ARCHIVED"
    assert versions[v2["id"]] == "PUBLISHED"


def test_create_version_reuses_existing_draft(client, designer_headers):
    """已存在草稿时再点「新建版本」应返回同一个草稿，而不是无限堆版本。"""
    template = _make_template(client, designer_headers)
    first = client.post(
        f"{BASE}/form-templates/{template['id']}/versions", headers=designer_headers, json={}
    ).json()
    second = client.post(
        f"{BASE}/form-templates/{template['id']}/versions", headers=designer_headers, json={}
    ).json()
    assert first["id"] == second["id"]


def test_publish_blocked_by_validation(client, designer_headers):
    template = _make_template(client, designer_headers)
    bad = {
        "sections": [
            {
                "key": "sec1",
                "title": "A",
                "fields": [{"key": "c", "label": "单选", "type": "radio", "options": []}],
            }
        ]
    }
    client.put(
        f"{BASE}/form-versions/{template['draft_version_id']}",
        headers=designer_headers,
        json={"schema_data": bad},
    )
    resp = client.post(
        f"{BASE}/form-versions/{template['draft_version_id']}/publish",
        headers=designer_headers,
        json={},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "FORM_SCHEMA_INVALID"


def test_validate_endpoint_separates_errors_and_warnings(client, designer_headers):
    template = _make_template(client, designer_headers)
    schema = {
        "sections": [
            {
                "key": "sec_apply",
                "title": "申请信息",
                "stage": "apply",
                "fields": [{"key": "a", "label": "A", "type": "text", "options": [
                    {"label": "x", "value": "x"}
                ]}],
            }
        ]
    }
    client.put(
        f"{BASE}/form-versions/{template['draft_version_id']}",
        headers=designer_headers,
        json={"schema_data": schema},
    )
    result = client.post(
        f"{BASE}/form-versions/{template['draft_version_id']}/validate",
        headers=designer_headers,
    ).json()
    # 文本字段配了选项 → 只是 warning，不阻断发布
    assert result["valid"] is True
    assert result["errors"] == []
    assert any(w["code"] == "OPTIONS_UNUSED" for w in result["warnings"])


# --------------------------------------------------------------------------- 预览


def test_preview_computes_formulas(client, designer_headers):
    template = _make_template(client, designer_headers)
    vid = template["draft_version_id"]
    client.put(
        f"{BASE}/form-versions/{vid}",
        headers=designer_headers,
        json={"schema_data": REIMBURSE_SCHEMA},
    )

    resp = client.post(
        f"{BASE}/form-versions/{vid}/preview",
        headers=designer_headers,
        json={
            "sample_data": {
                "reason": "出差",
                "items": [
                    {"name": "机票", "qty": 2, "price": 1200},
                    {"name": "住宿", "qty": 3, "price": 400},
                ],
            }
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # 子表行内小计与顶层合计都由服务端算好
    assert body["sample_data"]["items"][0]["subtotal"] == 2400
    assert body["sample_data"]["items"][1]["subtotal"] == 1200
    assert body["sample_data"]["total"] == 3600

    labels = {c["key"]: c["computed"] for c in body["computed_fields"]}
    assert labels["total"] == 3600
    assert labels["items[].subtotal"] == 2400


def test_preview_uses_default_values(client, designer_headers):
    template = _make_template(client, designer_headers)
    vid = template["draft_version_id"]
    client.put(
        f"{BASE}/form-versions/{vid}",
        headers=designer_headers,
        json={
            "schema_data": {
                "sections": [
                    {
                        "key": "s",
                        "title": "A",
                        "fields": [
                            {"key": "a", "label": "A", "type": "number", "default_value": 5},
                            {
                                "key": "double",
                                "label": "两倍",
                                "type": "formula",
                                "formula": {"type": "arithmetic", "expression": "a * 2"},
                            },
                        ],
                    }
                ]
            }
        },
    )
    body = client.post(
        f"{BASE}/form-versions/{vid}/preview", headers=designer_headers, json={}
    ).json()
    assert body["sample_data"]["a"] == 5
    assert body["sample_data"]["double"] == 10


# --------------------------------------------------------------------------- 导入导出


def test_export_import_roundtrip(client, designer_headers):
    template = _make_template(client, designer_headers)
    client.put(
        f"{BASE}/form-versions/{template['draft_version_id']}",
        headers=designer_headers,
        json={"schema_data": REIMBURSE_SCHEMA},
    )
    client.post(
        f"{BASE}/form-versions/{template['draft_version_id']}/publish",
        headers=designer_headers,
        json={},
    )

    exported = client.get(
        f"{BASE}/form-templates/{template['id']}/export", headers=designer_headers
    ).json()
    assert exported["name"] == "报销单"
    assert exported["schema_data"]["sections"][0]["key"] == "sec_apply"

    # 导出的 JSON 可直接回传导入（键名与导入接口对齐）
    imported = client.post(
        f"{BASE}/form-templates/import",
        headers=designer_headers,
        json={**exported, "name": "报销单(导入)", "code": "IMPORTED"},
    )
    assert imported.status_code == 201, imported.text

    new_version = client.get(
        f"{BASE}/form-versions/{imported.json()['draft_version_id']}", headers=designer_headers
    ).json()
    assert new_version["schema_data"]["sections"] == exported["schema_data"]["sections"]
