"""测试数据工厂与常用 API 动作。全部通过 HTTP。"""

from __future__ import annotations

import uuid
from typing import Any

from .client import ApiClient

TEST_PASSWORD = "testPass123"


def unique(prefix: str = "E2E") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def username(prefix: str = "e2e") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def create_user(
    admin: ApiClient,
    *,
    username_value: str,
    real_name: str = "E2E 用户",
    dept_id: int | None = None,
    role_ids: list[int] | None = None,
    password: str = TEST_PASSWORD,
) -> dict[str, Any]:
    response = admin.post(
        "users",
        json={
            "username": username_value,
            "password": password,
            "real_name": real_name,
            "dept_id": dept_id,
            "role_ids": role_ids or [],
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def create_dept(
    admin: ApiClient,
    *,
    name: str,
    code: str,
    parent_id: int | None = None,
    manager_user_id: int | None = None,
) -> dict[str, Any]:
    response = admin.post(
        "departments",
        json={
            "name": name,
            "code": code,
            "parent_id": parent_id,
            "manager_user_id": manager_user_id,
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def create_role(admin: ApiClient, *, code: str, name: str) -> dict[str, Any]:
    response = admin.post("roles", json={"code": code, "name": name})
    assert response.status_code in (200, 201), response.text
    return response.json()


def set_role_members(admin: ApiClient, role_id: int, user_ids: list[int]) -> None:
    response = admin.put(f"roles/{role_id}/members", json={"user_ids": user_ids})
    assert response.status_code == 200, response.text


def find_flow(admin: ApiClient, code: str) -> dict[str, Any]:
    response = admin.get("flow-templates?size=200")
    assert response.status_code == 200, response.text
    for flow in response.json():
        if flow.get("code") == code:
            return flow
    raise AssertionError(f"未找到流程模板：{code}")


def create_draft(
    client: ApiClient,
    flow_template_id: int,
    data: dict[str, Any],
    *,
    title: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        "instances/drafts",
        json={"flow_template_id": flow_template_id, "title": title, "data": data},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def update_draft(client: ApiClient, instance_id: int, data: dict[str, Any]) -> dict[str, Any]:
    response = client.put(f"instances/{instance_id}/draft", json={"data": data})
    assert response.status_code == 200, response.text
    return response.json()


def submit(
    client: ApiClient,
    instance_id: int,
    data: dict[str, Any],
    *,
    note: str = "",
    attachment_ids: list[int] | None = None,
    assignee_picks: dict[str, list[int]] | None = None,
    request_id: str | None = None,
) -> Any:
    headers = {"X-Request-Id": request_id} if request_id else None
    return client.post(
        f"instances/{instance_id}/submit",
        json={
            "data": data,
            "note": note,
            "attachment_ids": attachment_ids or [],
            "assignee_picks": assignee_picks or {},
        },
        headers=headers,
    )


def upload_file(
    client: ApiClient,
    *,
    filename: str = "e2e.txt",
    content: bytes = b"e2e attachment",
    content_type: str = "text/plain",
) -> Any:
    return client.post(
        "files/upload",
        files={"file": (filename, content, content_type)},
    )


def download_file(client: ApiClient, attachment_id: int) -> Any:
    return client.get(f"files/{attachment_id}/download")


def delete_file(client: ApiClient, attachment_id: int) -> Any:
    return client.delete(f"files/{attachment_id}")


def todo(client: ApiClient) -> list[dict[str, Any]]:
    response = client.get("tasks/todo?size=100")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def done(client: ApiClient) -> list[dict[str, Any]]:
    response = client.get("tasks/done?size=100")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def mine(client: ApiClient) -> list[dict[str, Any]]:
    response = client.get("tasks/mine?size=100")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def assignments_for(client: ApiClient, instance_id: int) -> list[dict[str, Any]]:
    return [item for item in todo(client) if item["instance_id"] == instance_id]


def find_assignment(
    client: ApiClient,
    instance_id: int,
    *,
    node_type: str | None = None,
) -> dict[str, Any]:
    items = assignments_for(client, instance_id)
    if node_type:
        items = [item for item in items if item.get("node_type") == node_type]
    assert items, f"未找到实例 {instance_id} 的待办（node_type={node_type}）"
    return items[0]


def act(
    client: ApiClient,
    assignment_id: int,
    *,
    action: str = "AGREE",
    opinion: str = "",
    attachment_ids: list[int] | None = None,
    field_patch: dict[str, Any] | None = None,
    return_target: str | None = None,
    request_id: str | None = None,
) -> Any:
    headers = {"X-Request-Id": request_id} if request_id else None
    body: dict[str, Any] = {
        "action": action,
        "opinion": opinion,
        "attachment_ids": attachment_ids or [],
        "field_patch": field_patch or {},
        "return_target": return_target,
    }
    return client.post(f"tasks/assignments/{assignment_id}/act", json=body, headers=headers)


def render(
    client: ApiClient,
    instance_id: int,
    *,
    assignment_id: int | None = None,
) -> Any:
    params = {"assignment_id": assignment_id} if assignment_id else None
    return client.get(f"instances/{instance_id}/render", params=params)


def resubmit(
    client: ApiClient,
    instance_id: int,
    data: dict[str, Any],
    *,
    note: str = "",
    request_id: str | None = None,
) -> Any:
    headers = {"X-Request-Id": request_id} if request_id else None
    return client.post(
        f"instances/{instance_id}/resubmit",
        json={"data": data, "note": note, "attachment_ids": [], "assignee_picks": {}},
        headers=headers,
    )


def withdraw(client: ApiClient, instance_id: int, *, reason: str = "") -> Any:
    return client.post(f"instances/{instance_id}/withdraw", json={"reason": reason})


def terminate(client: ApiClient, instance_id: int, *, reason: str) -> Any:
    return client.post(f"instances/{instance_id}/terminate", json={"reason": reason})


def cc_tasks(client: ApiClient) -> list[dict[str, Any]]:
    response = client.get("tasks/cc?size=100")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def archive(client: ApiClient, params: dict[str, Any] | None = None) -> Any:
    return client.get("instances/archive", params=params or {"size": 100})


def archive_export(client: ApiClient, params: dict[str, Any] | None = None) -> Any:
    return client.get("instances/archive/export", params=params or {})


def export_instance(client: ApiClient, instance_id: int) -> Any:
    return client.get(f"instances/{instance_id}/export")


def transfer(
    client: ApiClient,
    assignment_id: int,
    *,
    to_user_id: int,
    reason: str,
) -> Any:
    return client.post(
        f"tasks/assignments/{assignment_id}/transfer",
        json={"to_user_id": to_user_id, "reason": reason},
    )


def create_delegation(
    client: ApiClient,
    *,
    delegatee_id: int,
    start_at: str,
    end_at: str,
    reason: str,
    flow_template_ids: list[int] | None = None,
) -> Any:
    return client.post(
        "delegations",
        json={
            "delegatee_id": delegatee_id,
            "start_at": start_at,
            "end_at": end_at,
            "reason": reason,
            "flow_template_ids": flow_template_ids or [],
        },
    )


def cancel_delegation(client: ApiClient, delegation_id: int) -> Any:
    return client.post(f"delegations/{delegation_id}/cancel")


def start_reimburse(client: ApiClient, flow_id: int, *, amount: float, reason: str) -> int:
    data = reimburse_data(amount=amount, reason=reason)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def approve_reimburse(
    *,
    zhangsan: ApiClient,
    lisi: ApiClient,
    wangwu: ApiClient,
    admin: ApiClient,
    flow_id: int,
    amount: float = 2500,
    invoice: str = "INV-E2E-001",
    reason: str = "E2E 报销",
) -> int:
    """走完样例报销：部门经理 → 财务双签 → 财务填写 → 通过。"""
    instance_id = start_reimburse(zhangsan, flow_id, amount=amount, reason=reason)
    manager_task = find_assignment(lisi, instance_id)
    assert act(lisi, manager_task["assignment_id"], opinion="同意").status_code == 200

    finance_task = find_assignment(wangwu, instance_id)
    admin_task = find_assignment(admin, instance_id)
    assert act(wangwu, finance_task["assignment_id"], opinion="同意").status_code == 200
    assert act(admin, admin_task["assignment_id"], opinion="同意").status_code == 200

    fill_task = find_assignment(wangwu, instance_id, node_type="FILL")
    filled = act(
        wangwu,
        fill_task["assignment_id"],
        action="SUBMIT",
        opinion="核销完成",
        field_patch={"actualAmount": amount, "invoiceNo": invoice},
    )
    assert filled.status_code == 200, filled.text
    assert filled.json()["status"] == "APPROVED"
    return instance_id


def simple_form_schema(*, title_field: str = "reason") -> dict[str, Any]:
    return {
        "model_version": 1,
        "layout": {"label_position": "top", "columns": 1},
        "title_field": title_field,
        "rules": [],
        "sections": [
            {
                "key": "sec_apply",
                "title": "申请",
                "stage": "apply",
                "sort": 0,
                "fields": [
                    {
                        "key": "reason",
                        "label": "事由",
                        "type": "text",
                        "sort": 0,
                        "required": True,
                        "visible_at_start": True,
                    },
                    {
                        "key": "amount",
                        "label": "金额",
                        "type": "number",
                        "sort": 1,
                        "required": False,
                        "visible_at_start": True,
                    },
                ],
            }
        ],
    }


def full_form_schema() -> dict[str, Any]:
    return {
        "model_version": 1,
        "layout": {"label_position": "top", "columns": 3},
        "title_field": "title_text",
        "rules": [],
        "sections": [
            {
                "key": "sec_apply",
                "title": "全部控件",
                "stage": "apply",
                "sort": 0,
                "columns": 2,
                "collapsible": True,
                "fields": [
                    {"key": "title_text", "label": "标题文本", "type": "text", "sort": 0,
                     "required": True, "visible_at_start": True},
                    {"key": "long_text", "label": "多行文本", "type": "textarea", "sort": 1,
                     "required": False, "visible_at_start": True},
                    {"key": "qty", "label": "数量", "type": "number", "sort": 2,
                     "required": False, "visible_at_start": True},
                    {"key": "double", "label": "两倍", "type": "formula", "sort": 3,
                     "visible_at_start": True,
                     "formula": {"type": "arithmetic", "expression": "qty * 2"}},
                    {"key": "radio_pick", "label": "单选", "type": "radio", "sort": 4,
                     "visible_at_start": True,
                     "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]},
                    {"key": "checks", "label": "多选", "type": "checkbox", "sort": 5,
                     "visible_at_start": True,
                     "options": [{"label": "X", "value": "x"}, {"label": "Y", "value": "y"}]},
                    {"key": "category", "label": "类别", "type": "select", "sort": 6,
                     "visible_at_start": True,
                     "options": [{"label": "差旅", "value": "travel"},
                                 {"label": "办公", "value": "office"}]},
                    {"key": "sub_category", "label": "明细类别", "type": "cascader", "sort": 7,
                     "visible_at_start": True,
                     "cascader": {"parent_field": "category",
                                  "options_by_parent": {
                                      "travel": [{"label": "机票", "value": "flight"}],
                                      "office": [{"label": "文具", "value": "supply"}],
                                  }}},
                    {"key": "day", "label": "日期", "type": "date", "sort": 8,
                     "visible_at_start": True},
                    {"key": "clock", "label": "时间", "type": "time", "sort": 9,
                     "visible_at_start": True},
                    {"key": "moment", "label": "日期时间", "type": "datetime", "sort": 10,
                     "visible_at_start": True},
                    {"key": "urgent", "label": "紧急", "type": "switch", "sort": 11,
                     "visible_at_start": True},
                    {"key": "owner", "label": "负责人", "type": "user", "sort": 12,
                     "visible_at_start": True},
                    {"key": "reviewers", "label": "复核人", "type": "user_multi", "sort": 13,
                     "visible_at_start": True},
                    {"key": "dept", "label": "部门", "type": "dept", "sort": 14,
                     "visible_at_start": True},
                    {"key": "depts", "label": "协作部门", "type": "dept_multi", "sort": 15,
                     "visible_at_start": True},
                    {"key": "files", "label": "附件", "type": "attachment", "sort": 16,
                     "visible_at_start": True},
                    {"key": "pictures", "label": "图片", "type": "image", "sort": 17,
                     "visible_at_start": True},
                    {"key": "items", "label": "明细", "type": "subtable", "sort": 18,
                     "visible_at_start": True,
                     "columns": [
                         {"key": "name", "label": "项目", "type": "text", "sort": 0,
                          "required": True},
                         {"key": "amount", "label": "小计", "type": "number", "sort": 1},
                     ]},
                    {"key": "intro", "label": "说明", "type": "rich_text", "sort": 19,
                     "display": {"markdown": "**请如实填写**"}},
                    {"key": "head", "label": "标题", "type": "heading", "sort": 20,
                     "display": {"text": "申请信息", "level": 1}},
                    {"key": "para", "label": "段落", "type": "paragraph", "sort": 21,
                     "display": {"text": "请逐项填写"}},
                    {"key": "line", "label": "分割线", "type": "divider", "sort": 22,
                     "display": {}},
                    {"key": "banner", "label": "横幅", "type": "image_view", "sort": 23,
                     "display": {"url": "https://example.com/banner.png", "alt": "banner"}},
                ],
            }
        ],
    }


def full_data(*, owner: int, reviewer: int, dept: int, other_dept: int) -> dict[str, Any]:
    return {
        "title_text": "全控件表单",
        "long_text": "多行\n文本",
        "qty": 10,
        "radio_pick": "a",
        "checks": ["x", "y"],
        "category": "travel",
        "sub_category": "flight",
        "day": "2026-11-20",
        "clock": "10:30",
        "moment": "2026-11-20T10:30:00",
        "urgent": True,
        "owner": owner,
        "reviewers": [owner, reviewer],
        "dept": dept,
        "depts": [dept, other_dept],
        "files": [],
        "pictures": [],
        "items": [{"name": "项目一", "amount": 3}],
    }


def attachment_form_schema() -> dict[str, Any]:
    return {
        "model_version": 1,
        "layout": {"label_position": "top", "columns": 1},
        "title_field": "reason",
        "rules": [],
        "sections": [
            {
                "key": "sec_apply",
                "title": "申请",
                "stage": "apply",
                "sort": 0,
                "fields": [
                    {"key": "reason", "label": "事由", "type": "text", "sort": 0,
                     "required": True, "visible_at_start": True},
                    {"key": "secret_file", "label": "补充附件", "type": "attachment",
                     "sort": 1, "required": False, "visible_at_start": False},
                ],
            }
        ],
    }


def fill_then_approval_attachment_definition(
    *,
    fill_user_id: int,
    approver_user_id: int,
) -> dict[str, Any]:
    definition = fill_then_approval_definition(
        fill_user_id=fill_user_id,
        approver_user_id=approver_user_id,
    )
    # 填写节点开放附件字段
    definition["steps"][0]["fields_permission"]["overrides"] = {
        "secret_file": "editable-required"
    }
    return definition


def search_form_schema() -> dict[str, Any]:
    return {
        "model_version": 1,
        "layout": {"label_position": "top", "columns": 1},
        "title_field": "reason",
        "rules": [],
        "sections": [
            {
                "key": "sec_apply",
                "title": "申请",
                "stage": "apply",
                "sort": 0,
                "fields": [
                    {"key": "reason", "label": "事由", "type": "text", "sort": 0,
                     "required": True, "visible_at_start": True},
                    {"key": "amount", "label": "金额", "type": "number", "sort": 1,
                     "required": False, "visible_at_start": True},
                    {"key": "leaveDate", "label": "日期", "type": "date", "sort": 2,
                     "required": False, "visible_at_start": True},
                    {"key": "urgent", "label": "紧急", "type": "switch", "sort": 3,
                     "required": False, "visible_at_start": True},
                    {"key": "category", "label": "类别", "type": "select", "sort": 4,
                     "required": False, "visible_at_start": True,
                     "options": [
                         {"label": "差旅", "value": "travel"},
                         {"label": "办公", "value": "office"},
                     ]},
                    {"key": "tags", "label": "标签", "type": "checkbox", "sort": 5,
                     "required": False, "visible_at_start": True,
                     "options": [
                         {"label": "紧急", "value": "urgent"},
                         {"label": "普通", "value": "normal"},
                     ]},
                    {"key": "owner", "label": "负责人", "type": "user", "sort": 6,
                     "required": False, "visible_at_start": True},
                    {"key": "dept", "label": "部门", "type": "dept", "sort": 7,
                     "required": False, "visible_at_start": True},
                ],
            }
        ],
    }


def search_data(
    *,
    reason: str,
    amount: float,
    leave_date: str,
    urgent: bool,
    category: str,
    tags: list[str],
    owner: int,
    dept: int,
) -> dict[str, Any]:
    return {
        "reason": reason,
        "amount": amount,
        "leaveDate": leave_date,
        "urgent": urgent,
        "category": category,
        "tags": tags,
        "owner": owner,
        "dept": dept,
    }


def hidden_form_schema() -> dict[str, Any]:
    schema = simple_form_schema()
    schema["sections"][0]["fields"].append(
        {
            "key": "secret",
            "label": "补充信息",
            "type": "text",
            "sort": 2,
            "required": False,
            "visible_at_start": False,
        }
    )
    return schema


def create_form_and_publish(
    admin: ApiClient, *, name: str, schema: dict[str, Any] | None = None
) -> dict[str, Any]:
    code = f"E2E_FORM_{uuid.uuid4().hex[:8].upper()}"
    response = admin.post(
        "form-templates",
        json={"name": name, "code": code, "schema_data": schema or simple_form_schema()},
    )
    assert response.status_code in (200, 201), response.text
    form = response.json()
    versions = admin.get(f"form-templates/{form['id']}/versions")
    assert versions.status_code == 200, versions.text
    draft = next(v for v in versions.json() if v["status"] == "DRAFT")
    published = admin.post(
        f"form-versions/{draft['id']}/publish", json={"remark": "E2E 自动发布"}
    )
    assert published.status_code == 200, published.text
    return form


def _approval_node(
    node_id: str,
    name: str,
    assignee: dict[str, Any],
    *,
    return_targets: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "name": name,
        "type": "approval",
        "assignee": assignee,
        "reject_policy": "reject_to_initiator",
        "return_targets": return_targets,
        "timeout_hours": None,
        "opinion_required": False,
        "attachment_required": False,
        "fields_permission": {
            "base": "readonly",
            "partitions": {},
            "overrides": {},
            "conditional_overrides": [],
        },
    }


def dept_manager_rule() -> dict[str, Any]:
    return {
        "mode": "SINGLE",
        "sources": [{"type": "dept_manager"}],
        "on_empty": "to_admin",
        "initiator_select": None,
    }


def user_rule(user_id: int) -> dict[str, Any]:
    return {
        "mode": "SINGLE",
        "sources": [{"type": "user", "user_ids": [user_id]}],
        "on_empty": "to_admin",
        "initiator_select": None,
    }


def sequential_definition(approvals: list[tuple[str, str, int]]) -> dict[str, Any]:
    """approvals: [(node_id, node_name, user_id), ...]，依次审批。"""
    return {
        "model_version": 1,
        "start": {"id": "start", "name": "开始", "type": "start", "fields_permission": None},
        "steps": [
            _approval_node(node_id, name, user_rule(user_id))
            for node_id, name, user_id in approvals
        ],
        "end": {"id": "end", "name": "结束", "type": "end"},
    }


def dept_manager_chain_definition(count: int = 2) -> dict[str, Any]:
    return {
        "model_version": 1,
        "start": {"id": "start", "name": "开始", "type": "start", "fields_permission": None},
        "steps": [
            _approval_node(f"a{index}", f"主管审批{index}", dept_manager_rule())
            for index in range(1, count + 1)
        ],
        "end": {"id": "end", "name": "结束", "type": "end"},
    }


def parallel_any_definition(user_ids: list[int]) -> dict[str, Any]:
    return {
        "model_version": 1,
        "start": {"id": "start", "name": "开始", "type": "start", "fields_permission": None},
        "steps": [
            {
                "id": "p1",
                "name": "或签",
                "type": "parallel",
                "mode": "any",
                "members": [
                    _approval_node(f"m{index}", f"或签成员{index}", user_rule(user_id))
                    for index, user_id in enumerate(user_ids, start=1)
                ],
            }
        ],
        "end": {"id": "end", "name": "结束", "type": "end"},
    }


def parallel_all_definition(user_ids: list[int]) -> dict[str, Any]:
    return {
        "model_version": 1,
        "start": {"id": "start", "name": "开始", "type": "start", "fields_permission": None},
        "steps": [
            {
                "id": "p1",
                "name": "会签",
                "type": "parallel",
                "mode": "all",
                "members": [
                    _approval_node(f"m{index}", f"会签成员{index}", user_rule(user_id))
                    for index, user_id in enumerate(user_ids, start=1)
                ],
            }
        ],
        "end": {"id": "end", "name": "结束", "type": "end"},
    }


def parallel_return_definition(
    *,
    target_node_id: str,
    member_user_ids: list[int],
) -> dict[str, Any]:
    """A → 并行组（all）→ end；组内成员可退回 A。"""
    return {
        "model_version": 1,
        "start": {"id": "start", "name": "开始", "type": "start", "fields_permission": None},
        "steps": [
            _approval_node("a1", "退回目标审批", user_rule(member_user_ids[0])),
            {
                "id": "p1",
                "name": "并行组",
                "type": "parallel",
                "mode": "all",
                "members": [
                    _approval_node(
                        f"m{index}",
                        f"并行成员{index}",
                        user_rule(user_id),
                        return_targets=[target_node_id],
                    )
                    for index, user_id in enumerate(member_user_ids, start=1)
                ],
            },
        ],
        "end": {"id": "end", "name": "结束", "type": "end"},
    }


def create_flow_and_publish(
    admin: ApiClient,
    *,
    form_template_id: int,
    name: str,
    definition: dict[str, Any],
    initiator_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    code = f"E2E_FLOW_{uuid.uuid4().hex[:8].upper()}"
    response = admin.post(
        "flow-templates",
        json={
            "name": name,
            "code": code,
            "form_template_id": form_template_id,
            "initiator_scope": initiator_scope or {"type": "all"},
        },
    )
    assert response.status_code in (200, 201), response.text
    flow = response.json()
    versions = admin.get(f"flow-templates/{flow['id']}/versions")
    assert versions.status_code == 200, versions.text
    draft = next(v for v in versions.json() if v["status"] == "DRAFT")
    saved = admin.put(
        f"flow-versions/{draft['id']}", json={"definition": definition}
    )
    assert saved.status_code == 200, saved.text
    published = admin.post(
        f"flow-versions/{draft['id']}/publish", json={"remark": "E2E 自动发布"}
    )
    assert published.status_code == 200, published.text
    return flow


def _fill_node(
    node_id: str,
    name: str,
    assignee: dict[str, Any],
    *,
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "name": name,
        "type": "fill",
        "assignee": assignee,
        "return_targets": None,
        "timeout_hours": None,
        "fields_permission": {
            "base": "hidden",
            "partitions": {},
            "overrides": overrides or {},
            "conditional_overrides": [],
        },
    }


def fill_then_approval_definition(
    *,
    fill_user_id: int,
    approver_user_id: int,
) -> dict[str, Any]:
    return {
        "model_version": 1,
        "start": {"id": "start", "name": "开始", "type": "start", "fields_permission": None},
        "steps": [
            _fill_node(
                "f1",
                "补充信息",
                user_rule(fill_user_id),
                overrides={"secret": "editable-required"},
            ),
            _approval_node("a1", "复核审批", user_rule(approver_user_id)),
        ],
        "end": {"id": "end", "name": "结束", "type": "end"},
    }


def create_flow_draft(
    admin: ApiClient,
    *,
    form_template_id: int,
    name: str,
) -> tuple[dict[str, Any], int]:
    """只建流程草稿，不发布；返回 (flow, version_id)。"""
    response = admin.post(
        "flow-templates",
        json={
            "name": name,
            "form_template_id": form_template_id,
            "initiator_scope": {"type": "all"},
        },
    )
    assert response.status_code in (200, 201), response.text
    flow = response.json()
    versions = admin.get(f"flow-templates/{flow['id']}/versions")
    assert versions.status_code == 200, versions.text
    draft = next(v for v in versions.json() if v["status"] == "DRAFT")
    return flow, draft["id"]


def publish_definition(
    admin: ApiClient,
    version_id: int,
    definition: dict[str, Any],
) -> Any:
    saved = admin.put(f"flow-versions/{version_id}", json={"definition": definition})
    assert saved.status_code == 200, saved.text
    return admin.post(
        f"flow-versions/{version_id}/publish", json={"remark": "E2E 校验"}
    )


def role_rule(role_id: int) -> dict[str, Any]:
    return {
        "mode": "SINGLE",
        "sources": [{"type": "role", "role_ids": [role_id]}],
        "on_empty": "to_admin",
        "initiator_select": None,
    }


def prev_node_rule() -> dict[str, Any]:
    return {
        "mode": "SINGLE",
        "sources": [{"type": "prev_node_actors"}],
        "on_empty": "to_admin",
        "initiator_select": None,
    }


def simple_data(*, reason: str = "E2E 自建流程", amount: float = 100) -> dict[str, Any]:
    return {"reason": reason, "amount": amount}


def leave_data(*, reason: str = "E2E 请假") -> dict[str, Any]:
    return {
        "leaveType": "personal",
        "startDate": "2026-11-19",
        "endDate": "2026-11-19",
        "reason": reason,
    }


def reimburse_data(*, amount: float = 2500, reason: str = "E2E 报销") -> dict[str, Any]:
    return {
        "reason": reason,
        "category": "travel",
        "subCategory": "flight",
        "items": [{"name": "机票", "qty": 1, "price": amount}],
    }
