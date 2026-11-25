"""流程模板 / 版本接口测试（F2.x）。"""

from __future__ import annotations

BASE = "/api/v1"

REIMBURSE_FORM = {
    "sections": [
        {
            "key": "sec_apply", "title": "申请信息", "stage": "apply",
            "fields": [
                {"key": "reason", "label": "事由", "type": "text", "required": True},
                {"key": "amount", "label": "金额", "type": "number"},
                {"key": "applyDept", "label": "申请部门", "type": "dept"},
            ],
        },
        {
            "key": "sec_supplement", "title": "财务补充", "stage": "supplement",
            "fields": [
                {"key": "actualAmount", "label": "实际核销", "type": "number",
                 "visible_at_start": False},
            ],
        },
    ]
}

REIMBURSE_FLOW = {
    "steps": [
        {
            "id": "s1", "type": "approval", "name": "部门经理审批",
            "assignee": {"mode": "SINGLE", "sources": [{"type": "dept_manager"}]},
        },
        {
            "id": "s2", "type": "condition", "name": "按金额分流",
            "branches": [
                {"id": "b1",
                 "when": {"op": "and", "conditions": [{"field": "amount", "cmp": ">", "value": 2000}]},
                 "steps": [{
                     "id": "s3", "type": "parallel", "name": "财务双签", "mode": "all",
                     "members": [
                         {"id": "s3a", "type": "approval", "name": "会计审批",
                          "assignee": {"sources": [{"type": "role", "role_ids": [1]}]}},
                         {"id": "s3b", "type": "approval", "name": "复核审批",
                          "assignee": {"sources": [{"type": "role", "role_ids": [1]}]}},
                     ],
                 }]},
                {"id": "b2", "when": None, "steps": []},
            ],
        },
        {
            "id": "s4", "type": "fill", "name": "财务补充核销",
            "assignee": {"sources": [{"type": "role", "role_ids": [1]}]},
            "fields_permission": {
                "base": "hidden",
                "overrides": {"actualAmount": "editable-required"},
            },
        },
        {
            "id": "s5", "type": "cc", "name": "抄送财务总监",
            "cc_to": {"sources": [{"type": "role", "role_ids": [1]}]},
        },
    ]
}


def _published_form(client, headers, name="报销单") -> int:
    """建一个表单并发布，返回 form_template_id。"""
    template = client.post(
        f"{BASE}/form-templates", headers=headers, json={"name": name}
    ).json()
    client.put(
        f"{BASE}/form-versions/{template['draft_version_id']}",
        headers=headers, json={"schema_data": REIMBURSE_FORM},
    )
    client.post(
        f"{BASE}/form-versions/{template['draft_version_id']}/publish", headers=headers, json={}
    )
    return template["id"]


def _flow(client, headers, form_template_id, **overrides) -> dict:
    payload = {
        "name": "费用报销流程",
        "form_template_id": form_template_id,
        **overrides,
    }
    resp = client.post(f"{BASE}/flow-templates", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------- 权限


def test_flow_endpoints_require_designer(client, normal_headers):
    assert client.get(f"{BASE}/flow-templates", headers=normal_headers).status_code == 403
    assert client.post(
        f"{BASE}/flow-templates", headers=normal_headers, json={"name": "x", "form_template_id": 1}
    ).status_code == 403
    assert client.get(f"{BASE}/flow-templates").status_code == 401


# --------------------------------------------------------------------------- 模板


def test_create_flow_binds_form_template(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)

    assert template["status"] == "DRAFT"
    assert template["form_template_id"] == form_id
    assert template["form_template_name"] == "报销单"
    assert template["draft_version_id"] is not None
    assert template["initiator_scope"] == {"type": "all"}


def test_create_rejects_disabled_form(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    client.post(f"{BASE}/form-templates/{form_id}/status", headers=designer_headers,
                json={"status": "DISABLED"})

    resp = client.post(
        f"{BASE}/flow-templates", headers=designer_headers,
        json={"name": "x", "form_template_id": form_id},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "FORM_TEMPLATE_DISABLED"


def test_default_definition_is_usable(client, designer_headers):
    """新建流程自带一个「部门经理审批」节点，开箱即可校验通过。"""
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)

    result = client.post(
        f"{BASE}/flow-versions/{template['draft_version_id']}/validate",
        headers=designer_headers,
    ).json()
    assert result["valid"] is True, result["errors"]


def test_initiator_scope_roundtrip(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(
        client, designer_headers, form_id,
        initiator_scope={"type": "role", "role_ids": [1, 2]},
    )
    assert template["initiator_scope"]["type"] == "role"
    assert template["initiator_scope"]["role_ids"] == [1, 2]


def test_list_filter_and_keyword(client, designer_headers):
    """筛选按条件收窄。

    断言用「包含」而不是「恰好等于」：首启会写入**示例流程库**（M6），
    关键词「请假」同时命中示例里的「请假申请」—— 早先的
    `== ["请假流程"]` 依赖「库里只有本用例建的两条」，示例库一来就碎了。
    """
    form_id = _published_form(client, designer_headers)
    _flow(client, designer_headers, form_id, name="报销流程", code="F1", category="财务")
    _flow(client, designer_headers, form_id, name="请假流程", code="F2", category="人事")

    by_category = client.get(
        f"{BASE}/flow-templates", headers=designer_headers, params={"category": "财务"}
    ).json()
    assert [t["name"] for t in by_category] == ["报销流程"]

    by_keyword = client.get(
        f"{BASE}/flow-templates", headers=designer_headers, params={"keyword": "请假"}
    ).json()
    names = [t["name"] for t in by_keyword]
    assert "请假流程" in names
    assert all("请假" in n for n in names)   # 命中的都该含关键字

    by_form = client.get(
        f"{BASE}/flow-templates", headers=designer_headers,
        params={"form_template_id": form_id},
    ).json()
    assert len(by_form) == 2


def test_update_and_delete(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)

    updated = client.put(
        f"{BASE}/flow-templates/{template['id']}",
        headers=designer_headers,
        json={"name": "改过的流程", "category": "财务"},
    ).json()
    assert updated["name"] == "改过的流程"

    assert client.delete(
        f"{BASE}/flow-templates/{template['id']}", headers=designer_headers
    ).status_code == 200
    assert client.get(
        f"{BASE}/flow-templates/{template['id']}", headers=designer_headers
    ).status_code == 404


def test_duplicate_code_conflicts(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    _flow(client, designer_headers, form_id, code="DUP")
    resp = client.post(
        f"{BASE}/flow-templates", headers=designer_headers,
        json={"name": "另一个", "form_template_id": form_id, "code": "DUP"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "FLOW_CODE_EXISTS"


# --------------------------------------------------------------------------- 版本与发布


def test_save_definition(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    vid = template["draft_version_id"]

    resp = client.put(
        f"{BASE}/flow-versions/{vid}", headers=designer_headers,
        json={"definition": REIMBURSE_FLOW},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["definition"]["steps"]) == 4

    # 列表页的节点数应反映出来（审批/填写/抄送，不含条件与并行容器）
    listed = client.get(f"{BASE}/flow-templates", headers=designer_headers).json()
    assert listed[0]["node_count"] == 5   # s1 + s3a + s3b + s4 + s5


def test_save_rejects_malformed_shape(client, designer_headers):
    """形状错误（未知节点类型）在请求解析阶段就被拒。"""
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    resp = client.put(
        f"{BASE}/flow-versions/{template['draft_version_id']}",
        headers=designer_headers,
        json={"definition": {"steps": [{"id": "x", "type": "nope", "name": "X"}]}},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_save_allows_incomplete_flow(client, designer_headers):
    """保存不做语义校验 —— 设计器要能存下还没配审批人的节点。"""
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)

    resp = client.put(
        f"{BASE}/flow-versions/{template['draft_version_id']}",
        headers=designer_headers,
        json={"definition": {"steps": [
            {"id": "s1", "type": "approval", "name": "还没配审批人", "assignee": {"sources": []}}
        ]}},
    )
    assert resp.status_code == 200, resp.text

    result = client.post(
        f"{BASE}/flow-versions/{template['draft_version_id']}/validate",
        headers=designer_headers,
    ).json()
    assert result["valid"] is False
    assert any(e["code"] == "NO_ASSIGNEE" for e in result["errors"])


def test_validate_catches_field_reference_errors(client, designer_headers):
    """F2.7：条件引用了表单里不存在的字段要能查出来。"""
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)

    client.put(
        f"{BASE}/flow-versions/{template['draft_version_id']}",
        headers=designer_headers,
        json={"definition": {"steps": [
            {"id": "s1", "type": "approval", "name": "A",
             "assignee": {"sources": [{"type": "user", "user_ids": [1]}]}},
            {"id": "c1", "type": "condition", "name": "分流", "branches": [
                {"id": "b1",
                 "when": {"conditions": [{"field": "ghost", "cmp": ">", "value": 1}]},
                 "steps": []},
                {"id": "b2", "when": None, "steps": []},
            ]},
        ]}},
    )
    result = client.post(
        f"{BASE}/flow-versions/{template['draft_version_id']}/validate",
        headers=designer_headers,
    ).json()
    assert result["valid"] is False
    assert any(e["code"] == "CONDITION_FIELD_MISSING" for e in result["errors"])


def test_publish_locks_form_version(client, designer_headers):
    """F2.6：发布流程版本时锁定表单版本。"""
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    vid = template["draft_version_id"]

    client.put(
        f"{BASE}/flow-versions/{vid}", headers=designer_headers,
        json={"definition": REIMBURSE_FLOW},
    )
    published = client.post(
        f"{BASE}/flow-versions/{vid}/publish", headers=designer_headers, json={}
    )
    assert published.status_code == 200, published.text
    body = published.json()
    assert body["status"] == "PUBLISHED"
    assert body["locked_form_version_no"] == 1

    after = client.get(f"{BASE}/flow-templates/{template['id']}", headers=designer_headers).json()
    assert after["status"] == "PUBLISHED"
    assert after["current_version_id"] == vid
    assert after["locked_form_version_no"] == 1


def test_publish_requires_form_published(client, designer_headers):
    """表单没发布过就不能发布流程 —— 否则实例拿不到稳定的 schema。"""
    template_form = client.post(
        f"{BASE}/form-templates", headers=designer_headers, json={"name": "未发布的表单"}
    ).json()
    form_id = template_form["id"]

    flow = client.post(
        f"{BASE}/flow-templates", headers=designer_headers,
        json={"name": "流程", "form_template_id": form_id},
    ).json()

    resp = client.post(
        f"{BASE}/flow-versions/{flow['draft_version_id']}/publish",
        headers=designer_headers, json={},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "FORM_NOT_PUBLISHED"


def test_published_version_not_editable(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    vid = template["draft_version_id"]
    client.post(f"{BASE}/flow-versions/{vid}/publish", headers=designer_headers, json={})

    resp = client.put(
        f"{BASE}/flow-versions/{vid}", headers=designer_headers,
        json={"definition": REIMBURSE_FLOW},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VERSION_NOT_EDITABLE"


def test_new_version_forks_from_published(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    v1 = template["draft_version_id"]

    client.put(f"{BASE}/flow-versions/{v1}", headers=designer_headers,
               json={"definition": REIMBURSE_FLOW})
    client.post(f"{BASE}/flow-versions/{v1}/publish", headers=designer_headers, json={})

    v2 = client.post(
        f"{BASE}/flow-templates/{template['id']}/versions", headers=designer_headers
    ).json()
    assert v2["version_no"] == 2
    assert v2["status"] == "DRAFT"
    assert len(v2["definition"]["steps"]) == 4     # 承袭 v1

    # 新建草稿**不会**让已发布版本归档 —— 归档发生在新版本发布时。
    # 否则设计器一开新草稿，运行中实例引用的版本就被标成归档了。
    versions = {
        v["id"]: v["status"]
        for v in client.get(
            f"{BASE}/flow-templates/{template['id']}/versions", headers=designer_headers
        ).json()
    }
    assert versions[v1] == "PUBLISHED"
    assert versions[v2["id"]] == "DRAFT"

    client.post(f"{BASE}/flow-versions/{v2['id']}/publish", headers=designer_headers, json={})
    versions = {
        v["id"]: v["status"]
        for v in client.get(
            f"{BASE}/flow-templates/{template['id']}/versions", headers=designer_headers
        ).json()
    }
    assert versions[v1] == "ARCHIVED"
    assert versions[v2["id"]] == "PUBLISHED"


def test_create_version_reuses_existing_draft(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)

    first = client.post(
        f"{BASE}/flow-templates/{template['id']}/versions", headers=designer_headers
    ).json()
    second = client.post(
        f"{BASE}/flow-templates/{template['id']}/versions", headers=designer_headers
    ).json()
    assert first["id"] == second["id"]


def test_publish_blocked_by_validation(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    vid = template["draft_version_id"]

    client.put(
        f"{BASE}/flow-versions/{vid}", headers=designer_headers,
        json={"definition": {"steps": [
            {"id": "s1", "type": "approval", "name": "没有审批人", "assignee": {"sources": []}}
        ]}},
    )
    resp = client.post(f"{BASE}/flow-versions/{vid}/publish", headers=designer_headers, json={})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "FLOW_INVALID"
    assert any(e["code"] == "NO_ASSIGNEE" for e in detail["extra"]["errors"])


def test_validate_warns_but_allows_publish(client, designer_headers):
    """warning 不阻断发布（例如条件没有 else 分支）。"""
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    vid = template["draft_version_id"]

    client.put(
        f"{BASE}/flow-versions/{vid}", headers=designer_headers,
        json={"definition": {"steps": [
            {"id": "s1", "type": "approval", "name": "A",
             "assignee": {"sources": [{"type": "user", "user_ids": [1]}]}},
            {"id": "c1", "type": "condition", "name": "无 else", "branches": [
                {"id": "b1",
                 "when": {"conditions": [{"field": "amount", "cmp": ">", "value": 1}]},
                 "steps": []},
            ]},
        ]}},
    )
    result = client.post(
        f"{BASE}/flow-versions/{vid}/validate", headers=designer_headers
    ).json()
    assert result["valid"] is True
    assert any(w["code"] == "NO_ELSE_BRANCH" for w in result["warnings"])

    assert client.post(
        f"{BASE}/flow-versions/{vid}/publish", headers=designer_headers, json={}
    ).status_code == 200


def test_delete_draft_version_only(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    vid = template["draft_version_id"]

    assert client.delete(
        f"{BASE}/flow-versions/{vid}", headers=designer_headers
    ).status_code == 200
    assert client.get(
        f"{BASE}/flow-versions/{vid}", headers=designer_headers
    ).status_code == 404


# --------------------------------------------------------------------------- 退回目标


def test_return_targets_endpoint(client, designer_headers):
    """设计器不该在前端重复实现「可退回给谁」的规则。"""
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    vid = template["draft_version_id"]
    client.put(f"{BASE}/flow-versions/{vid}", headers=designer_headers,
               json={"definition": REIMBURSE_FLOW})

    # s4 可退回 s1
    targets = client.get(
        f"{BASE}/flow-versions/{vid}/return-targets",
        headers=designer_headers, params={"node_id": "s4"},
    ).json()
    assert [t["id"] for t in targets] == ["s1"]

    # s1 是第一个节点，无处可退
    assert client.get(
        f"{BASE}/flow-versions/{vid}/return-targets",
        headers=designer_headers, params={"node_id": "s1"},
    ).json() == []

    # 并行组成员 s3a 可退回 s1
    targets_a = client.get(
        f"{BASE}/flow-versions/{vid}/return-targets",
        headers=designer_headers, params={"node_id": "s3a"},
    ).json()
    assert [t["id"] for t in targets_a] == ["s1"]


def test_return_targets_unknown_node(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    resp = client.get(
        f"{BASE}/flow-versions/{template['draft_version_id']}/return-targets",
        headers=designer_headers, params={"node_id": "ghost"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NODE_NOT_FOUND"


# --------------------------------------------------------------------------- 导入导出


def test_export_import_roundtrip(client, designer_headers):
    """F2.9：导出的 JSON 加上目标表单即可直接回传导入，定义保持原样。"""
    form_id = _published_form(client, designer_headers)
    template = _flow(
        client,
        designer_headers,
        form_id,
        code="EXPORT_FLOW",
        category="财务",
        initiator_scope={"type": "role", "role_ids": [1]},
    )
    vid = template["draft_version_id"]
    client.put(
        f"{BASE}/flow-versions/{vid}", headers=designer_headers,
        json={"definition": REIMBURSE_FLOW},
    )
    client.post(f"{BASE}/flow-versions/{vid}/publish", headers=designer_headers, json={})

    exported = client.get(
        f"{BASE}/flow-templates/{template['id']}/export", headers=designer_headers
    ).json()
    assert exported["name"] == "费用报销流程"
    assert exported["code"] == "EXPORT_FLOW"
    assert exported["category"] == "财务"
    assert exported["form_name"] == "报销单"
    assert exported["initiator_scope"]["type"] == "role"
    assert exported["initiator_scope"]["role_ids"] == [1]
    assert len(exported["definition"]["steps"]) == 4

    imported = client.post(
        f"{BASE}/flow-templates/import",
        headers=designer_headers,
        json={
            **exported,
            "name": "费用报销流程(导入)",
            "code": None,
            "form_template_id": form_id,
        },
    )
    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["name"] == "费用报销流程(导入)"
    assert body["status"] == "DRAFT"
    assert body["form_template_id"] == form_id
    assert body["current_version_id"] is None
    assert body["draft_version_id"] is not None

    version = client.get(
        f"{BASE}/flow-versions/{body['draft_version_id']}", headers=designer_headers
    ).json()
    assert version["definition"]["steps"] == exported["definition"]["steps"]
    assert version["status"] == "DRAFT"

    # 导入后无需改定义即可校验通过（组织引用是否有效由用户在目标环境梳理）
    result = client.post(
        f"{BASE}/flow-versions/{body['draft_version_id']}/validate",
        headers=designer_headers,
    ).json()
    assert result["valid"] is True, result["errors"]

    published = client.post(
        f"{BASE}/flow-versions/{body['draft_version_id']}/publish",
        headers=designer_headers,
        json={},
    )
    assert published.status_code == 200, published.text
    assert published.json()["locked_form_version_no"] == 1


def test_import_rejects_duplicate_code(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id, code="IMPORT_DUP")
    exported = client.get(
        f"{BASE}/flow-templates/{template['id']}/export", headers=designer_headers
    ).json()

    resp = client.post(
        f"{BASE}/flow-templates/import",
        headers=designer_headers,
        json={**exported, "form_template_id": form_id},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "FLOW_CODE_EXISTS"


def test_import_rejects_disabled_form(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    template = _flow(client, designer_headers, form_id)
    exported = client.get(
        f"{BASE}/flow-templates/{template['id']}/export", headers=designer_headers
    ).json()
    client.post(
        f"{BASE}/form-templates/{form_id}/status",
        headers=designer_headers,
        json={"status": "DISABLED"},
    )

    resp = client.post(
        f"{BASE}/flow-templates/import",
        headers=designer_headers,
        json={**exported, "form_template_id": form_id},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "FORM_TEMPLATE_DISABLED"


def test_import_rejects_malformed_definition(client, designer_headers):
    form_id = _published_form(client, designer_headers)
    resp = client.post(
        f"{BASE}/flow-templates/import",
        headers=designer_headers,
        json={
            "name": "坏流程",
            "form_template_id": form_id,
            "definition": {"steps": [{"id": "x", "type": "nope", "name": "X"}]},
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_export_import_require_designer(client, normal_headers):
    assert client.get(
        f"{BASE}/flow-templates/1/export", headers=normal_headers
    ).status_code == 403
    assert client.post(
        f"{BASE}/flow-templates/import",
        headers=normal_headers,
        json={"form_template_id": 1, "definition": {"steps": []}},
    ).status_code == 403
