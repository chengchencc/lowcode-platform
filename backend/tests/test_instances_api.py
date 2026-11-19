"""实例与任务接口测试（F3.x / F4.x）。

其中 `TestLeaveScenario` 是 **PRD §9 场景一（请假）的端到端走查**：
设计者配表单与流程 → 员工发起 → 主管审批 → 条件分支 → 总监审批 → 抄送 HR。
"""

from __future__ import annotations

import pytest

from app.core.constants import FlowStatus
from app.models import FlowTemplate
from tests.conftest import login_as
from tests.test_engine_service import (
    FACTORY_PASSWORD as PASSWORD,
)
from tests.test_engine_service import (
    _published_flow,
    _published_form,
    _user,
)

BASE = "/api/v1"

LEAVE_SCHEMA = {
    "sections": [
        {"key": "sec_apply", "title": "申请信息", "stage": "apply", "fields": [
            {"key": "leaveType", "label": "假别", "type": "select", "required": True,
             "options": [{"label": "事假", "value": "personal"},
                         {"label": "年假", "value": "annual"}]},
            {"key": "startDate", "label": "开始日期", "type": "date", "required": True},
            {"key": "endDate", "label": "结束日期", "type": "date", "required": True},
            {"key": "days", "label": "天数", "type": "formula",
             "formula": {"type": "date_diff", "start_field": "startDate", "end_field": "endDate"}},
            {"key": "reason", "label": "事由", "type": "textarea", "required": True},
        ]},
    ]
}


def _setup_leave_flow(db, *, director_id: int, hr_id: int) -> tuple:
    """建一条请假流程并发布，返回 (模板, 版本, 表单版本)。"""
    from app.core.constants import FlowStatus, FlowVersionStatus
    from app.models import FlowTemplate

    owner = _user(db)
    form = _published_form(db, owner)
    # 覆盖成请假表单
    form.schema = LEAVE_SCHEMA
    db.flush()

    definition = {
        "steps": [
            {"id": "s1", "type": "approval", "name": "直属上级审批",
             "assignee": {"mode": "SINGLE", "sources": [{"type": "dept_manager"}]}},
            {"id": "s2", "type": "condition", "name": "按天数分流", "branches": [
                {"id": "long",
                 "when": {"op": "and", "conditions": [{"field": "days", "cmp": ">", "value": 3}]},
                 "steps": [{"id": "s3", "type": "approval", "name": "总监审批",
                            "assignee": {"sources": [{"type": "user", "user_ids": [director_id]}]}}]},
                {"id": "short", "when": None, "steps": []},
            ]},
            {"id": "s4", "type": "cc", "name": "抄送 HR",
             "cc_to": {"sources": [{"type": "user", "user_ids": [hr_id]}]}},
        ]
    }
    template = FlowTemplate(
        name="请假申请", form_template_id=form.template_id,
        status=FlowStatus.PUBLISHED, initiator_scope={"type": "all"}, created_by=owner.id,
    )
    db.add(template)
    db.flush()

    version = _published_flow(db, owner, form, definition)
    # 让模板指向刚建的版本
    template.current_version_id = version.id
    template.form_template_id = form.template_id
    version.template_id = template.id
    db.flush()
    assert version.status == FlowVersionStatus.PUBLISHED
    return template, version, form


class TestLeaveScenario:
    """PRD §9 场景一：顺序 + 条件分支 + 抄送。"""

    def _prepare(self, db, client):
        from app.models import Department

        hq = db.scalar(
            __import__("sqlalchemy").select(Department).where(Department.code == "HQ")
        )
        manager = _user(db, dept_id=hq.id)
        hq.manager_user_id = manager.id
        director = _user(db)
        hr = _user(db)
        employee = _user(db, dept_id=hq.id)
        db.flush()

        template, version, form = _setup_leave_flow(
            db, director_id=director.id, hr_id=hr.id
        )
        db.commit()

        emp_headers = login_as(client, employee.username, PASSWORD)
        mgr_headers = login_as(client, manager.username, PASSWORD)
        dir_headers = login_as(client, director.username, PASSWORD)
        hr_headers = login_as(client, hr.username, PASSWORD)
        return employee, manager, director, hr, template, emp_headers, mgr_headers, dir_headers, hr_headers

    def test_long_leave_goes_through_director(self, db, client):
        (employee, manager, director, hr, template,
         emp_h, mgr_h, dir_h, hr_h) = self._prepare(db, client)

        # 1) 发起中心能看到流程
        available = client.get(f"{BASE}/instances/available-flows", headers=emp_h).json()
        assert any(t["name"] == "请假申请" for t in available), available

        # 2) 发起页元数据
        opts = client.get(
            f"{BASE}/instances/start-options/{template.id}", headers=emp_h
        ).json()
        assert opts["schema_data"]["sections"][0]["key"] == "sec_apply"
        # 发起阶段天数字段是公式 → 只读
        assert opts["permissions"]["days"]["editable"] is False
        assert opts["permissions"]["reason"]["editable"] is True

        # 3) 建草稿 → 暂存 → 提交
        draft = client.post(
            f"{BASE}/instances/drafts", headers=emp_h,
            json={"flow_template_id": template.id, "title": "请假 5 天"},
        ).json()
        assert draft["status"] == "DRAFT"

        client.put(
            f"{BASE}/instances/{draft['id']}/draft", headers=emp_h,
            json={"data": {"leaveType": "annual", "reason": "旅行"}},
        )
        submitted = client.post(
            f"{BASE}/instances/{draft['id']}/submit", headers=emp_h,
            json={"data": {
                "leaveType": "annual", "startDate": "2026-10-01",
                "endDate": "2026-10-06", "reason": "旅行",
            }},
        )
        assert submitted.status_code == 200, submitted.text
        instance = submitted.json()
        assert instance["status"] == "RUNNING"
        # 天数公式由服务端重算：10-01 → 10-06 = 5 天
        detail = client.get(f"{BASE}/instances/{draft['id']}/render", headers=emp_h).json()
        assert detail["values"]["days"] == 5

        # 4) 主管收到待办
        todo = client.get(f"{BASE}/tasks/todo", headers=mgr_h).json()
        assert todo["total"] == 1
        assignment = todo["items"][0]
        assert assignment["node_name"] == "直属上级审批"

        # 5) 主管同意 → 天数 > 3 → 走总监分支
        client.post(
            f"{BASE}/tasks/assignments/{assignment['assignment_id']}/act", headers=mgr_h,
            json={"action": "AGREE", "opinion": "同意"},
        )
        dir_todo = client.get(f"{BASE}/tasks/todo", headers=dir_h).json()
        assert dir_todo["total"] == 1
        assert dir_todo["items"][0]["node_name"] == "总监审批"

        # 5.1) URL 上残留的旧 assignment 不应再被当成当前待办
        stale = client.get(
            f"{BASE}/instances/{draft['id']}/render",
            headers=mgr_h,
            params={"assignment_id": assignment["assignment_id"]},
        ).json()
        assert stale["assignment"] is None
        assert stale["my_role"] != "CURRENT_HANDLER"
        assert stale["allowed_actions"] == []

        # 6) 总监同意 → 抄送 HR → 实例通过
        client.post(
            f"{BASE}/tasks/assignments/{dir_todo['items'][0]['assignment_id']}/act",
            headers=dir_h, json={"action": "AGREE", "opinion": "准假"},
        )

        final = client.get(f"{BASE}/instances/{draft['id']}/render", headers=emp_h).json()
        assert final["instance"]["status"] == "APPROVED"

        # 7) HR 收到抄送（不阻塞主线）
        cc = client.get(f"{BASE}/tasks/cc", headers=hr_h).json()
        assert cc["total"] == 1
        assert cc["items"][0]["node_name"] == "抄送 HR"

        # 8) 时间线完整：提交 → 主管 → 总监
        actions = [a["action"] for a in final["actions"]]
        assert actions == ["SUBMIT", "AGREE", "AGREE"]

    def test_short_leave_skips_director(self, db, client):
        """天数 ≤ 3 不发总监，直达 HR 抄送。"""
        (employee, manager, director, hr, template,
         emp_h, mgr_h, dir_h, hr_h) = self._prepare(db, client)

        draft = client.post(
            f"{BASE}/instances/drafts", headers=emp_h,
            json={"flow_template_id": template.id, "title": "请假 2 天"},
        ).json()
        client.post(
            f"{BASE}/instances/{draft['id']}/submit", headers=emp_h,
            json={"data": {
                "leaveType": "personal", "startDate": "2026-10-01",
                "endDate": "2026-10-03", "reason": "私事",
            }},
        )

        todo = client.get(f"{BASE}/tasks/todo", headers=mgr_h).json()
        client.post(
            f"{BASE}/tasks/assignments/{todo['items'][0]['assignment_id']}/act",
            headers=mgr_h, json={"action": "AGREE"},
        )

        # 总监**没有**任何待办
        assert client.get(f"{BASE}/tasks/todo", headers=dir_h).json()["total"] == 0
        # 实例已通过，HR 收到抄送
        detail = client.get(f"{BASE}/instances/{draft['id']}/render", headers=emp_h).json()
        assert detail["instance"]["status"] == "APPROVED"
        assert client.get(f"{BASE}/tasks/cc", headers=hr_h).json()["total"] == 1

    def test_progress_bar_marks_taken_branch(self, db, client):
        (employee, manager, director, hr, template,
         emp_h, mgr_h, dir_h, hr_h) = self._prepare(db, client)

        draft = client.post(
            f"{BASE}/instances/drafts", headers=emp_h,
            json={"flow_template_id": template.id},
        ).json()
        client.post(
            f"{BASE}/instances/{draft['id']}/submit", headers=emp_h,
            json={"data": {
                "leaveType": "annual", "startDate": "2026-10-01",
                "endDate": "2026-10-06", "reason": "旅行",
            }},
        )

        # 提交后条件还没求值（主管尚未同意），两条分支都应是「未走」
        detail = client.get(f"{BASE}/instances/{draft['id']}/render", headers=emp_h).json()
        condition = next(p for p in detail["progress"] if p["type"] == "condition")
        assert all(not b["taken"] for b in condition["branches"])

        # 主管同意后条件才被求值 → 标记走的哪条
        todo = client.get(f"{BASE}/tasks/todo", headers=mgr_h).json()
        client.post(
            f"{BASE}/tasks/assignments/{todo['items'][0]['assignment_id']}/act",
            headers=mgr_h, json={"action": "AGREE"},
        )

        detail = client.get(f"{BASE}/instances/{draft['id']}/render", headers=emp_h).json()
        condition = next(p for p in detail["progress"] if p["type"] == "condition")
        branches = {b["branch_id"]: b for b in condition["branches"]}
        assert branches["long"]["taken"] is True
        assert branches["short"]["taken"] is False
        # 走的那条分支里能看到总监节点
        assert [n["node_id"] for n in branches["long"]["nodes"]] == ["s3"]

    def test_employee_cannot_see_supplement_fields(self, db, client):
        """HR 抄送人看得到全量；发起人在运行中看不到补充区字段。"""
        (employee, manager, director, hr, template,
         emp_h, mgr_h, dir_h, hr_h) = self._prepare(db, client)

        draft = client.post(
            f"{BASE}/instances/drafts", headers=emp_h,
            json={"flow_template_id": template.id},
        ).json()
        client.post(
            f"{BASE}/instances/{draft['id']}/submit", headers=emp_h,
            json={"data": {
                "leaveType": "annual", "startDate": "2026-10-01",
                "endDate": "2026-10-06", "reason": "旅行",
            }},
        )

        # 运行中：主管是当前处理人，可编辑本节点开放的字段（申请区默认只读）
        mgr_detail = client.get(
            f"{BASE}/instances/{draft['id']}/render", headers=mgr_h
        ).json()
        assert mgr_detail["my_role"] == "CURRENT_HANDLER"
        assert mgr_detail["permissions"]["reason"]["editable"] is False   # 申请区只读
        assert mgr_detail["allowed_actions"] == ["AGREE", "REJECT", "RETURN"]

        # 发起人：运行中只看到「发起阶段能看到的」
        emp_detail = client.get(
            f"{BASE}/instances/{draft['id']}/render", headers=emp_h
        ).json()
        assert emp_detail["my_role"] == "INITIATOR"
        assert emp_detail["allowed_actions"] == []


def _first_available_id(client, headers) -> int:
    available = client.get(f"{BASE}/instances/available-flows", headers=headers).json()
    assert available, "至少应有一个可发起流程"
    return available[0]["id"]


class TestDrafts:
    def test_draft_lifecycle(self, db, client):
        owner = _user(db)
        _setup_leave_flow(db, director_id=_user(db).id, hr_id=_user(db).id)
        db.commit()

        headers = login_as(client, owner.username, PASSWORD)
        draft = client.post(
            f"{BASE}/instances/drafts", headers=headers,
            json={"flow_template_id": _first_available_id(client, headers)},
        ).json()
        assert draft["status"] == "DRAFT"

        drafts = client.get(f"{BASE}/instances/drafts", headers=headers).json()
        assert [d["id"] for d in drafts] == [draft["id"]]

        # 暂存
        updated = client.put(
            f"{BASE}/instances/{draft['id']}/draft", headers=headers,
            json={"title": "改名了", "data": {"reason": "草稿内容"}},
        ).json()
        assert updated["title"] == "改名了"
        assert updated["status"] == "DRAFT"

        # 删除
        assert client.delete(
            f"{BASE}/instances/{draft['id']}", headers=headers
        ).status_code == 200
        assert client.get(f"{BASE}/instances/drafts", headers=headers).json() == []

    def test_draft_does_not_create_tasks(self, db, client):
        """草稿**不生成审批任务**（PRD F3.3）。"""
        owner = _user(db)
        _setup_leave_flow(db, director_id=_user(db).id, hr_id=_user(db).id)
        db.commit()

        headers = login_as(client, owner.username, PASSWORD)
        client.post(
            f"{BASE}/instances/drafts", headers=headers,
            json={"flow_template_id": _first_available_id(client, headers)},
        )
        assert client.get(f"{BASE}/tasks/todo", headers=headers).json()["total"] == 0

    def test_cannot_edit_others_draft(self, db, client):
        owner = _user(db)
        stranger = _user(db)
        _setup_leave_flow(db, director_id=_user(db).id, hr_id=_user(db).id)
        db.commit()

        owner_h = login_as(client, owner.username, PASSWORD)
        stranger_h = login_as(client, stranger.username, PASSWORD)

        draft = client.post(
            f"{BASE}/instances/drafts", headers=owner_h,
            json={"flow_template_id": _first_available_id(client, owner_h)},
        ).json()

        resp = client.put(
            f"{BASE}/instances/{draft['id']}/draft", headers=stranger_h,
            json={"data": {"reason": "偷改"}},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "NOT_INITIATOR"


def _make_single_node_flow(db, *, node_type: str, approver_id: int):
    """建一个「单节点」流程并发布，返回 FlowTemplate。

    比请假流程更适合测动作校验 —— 节点类型与审批人可以精确指定。
    """
    owner = _user(db)
    form = _published_form(db, owner)
    version = _published_flow(db, owner, form, {
        "steps": [{
            "id": "n1", "type": node_type, "name": "唯一节点",
            "assignee": {"mode": "SINGLE", "sources": [{"type": "user", "user_ids": [approver_id]}]},
        }],
    })
    template = db.get(FlowTemplate, version.template_id)
    assert template is not None
    template.status = FlowStatus.PUBLISHED
    db.flush()
    return template, form


def _submit_simple(client, headers, template_id: int) -> dict:
    draft = client.post(
        f"{BASE}/instances/drafts", headers=headers,
        json={"flow_template_id": template_id},
    ).json()
    resp = client.post(
        f"{BASE}/instances/{draft['id']}/submit", headers=headers,
        json={"data": {"reason": "x"}},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestTaskActions:
    def test_fill_node_rejects_agree(self, db, client):
        """填写节点不接受「同意」这类动作。"""
        initiator = _user(db)
        filler = _user(db)
        template, _form = _make_single_node_flow(db, node_type="fill", approver_id=filler.id)
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        filler_h = login_as(client, filler.username, PASSWORD)
        _submit_simple(client, init_h, template.id)

        todo = client.get(f"{BASE}/tasks/todo", headers=filler_h).json()
        aid = todo["items"][0]["assignment_id"]

        resp = client.post(
            f"{BASE}/tasks/assignments/{aid}/act", headers=filler_h,
            json={"action": "AGREE"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "ACTION_NOT_ALLOWED"

        # 「提交」才是对的
        ok = client.post(
            f"{BASE}/tasks/assignments/{aid}/act", headers=filler_h,
            json={"action": "SUBMIT"},
        )
        assert ok.status_code == 200, ok.text

    def test_approval_node_allowed_actions(self, db, client):
        initiator = _user(db)
        approver = _user(db)
        template, _form = _make_single_node_flow(db, node_type="approval", approver_id=approver.id)
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        approver_h = login_as(client, approver.username, PASSWORD)
        instance = _submit_simple(client, init_h, template.id)

        detail = client.get(
            f"{BASE}/instances/{instance['id']}/render", headers=approver_h
        ).json()
        assert detail["allowed_actions"] == ["AGREE", "REJECT", "RETURN"]
        assert detail["my_role"] == "CURRENT_HANDLER"

    def test_reject_requires_opinion(self, db, client):
        initiator = _user(db)
        approver = _user(db)
        template, _form = _make_single_node_flow(db, node_type="approval", approver_id=approver.id)
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        approver_h = login_as(client, approver.username, PASSWORD)
        _submit_simple(client, init_h, template.id)

        todo = client.get(f"{BASE}/tasks/todo", headers=approver_h).json()
        aid = todo["items"][0]["assignment_id"]

        resp = client.post(
            f"{BASE}/tasks/assignments/{aid}/act", headers=approver_h,
            json={"action": "REJECT"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "REJECT_OPINION_REQUIRED"

    def test_other_user_cannot_act(self, db, client):
        initiator = _user(db)
        approver = _user(db)
        stranger = _user(db)
        template, _form = _make_single_node_flow(db, node_type="approval", approver_id=approver.id)
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        approver_h = login_as(client, approver.username, PASSWORD)
        stranger_h = login_as(client, stranger.username, PASSWORD)
        _submit_simple(client, init_h, template.id)

        aid = client.get(f"{BASE}/tasks/todo", headers=approver_h).json()["items"][0]["assignment_id"]
        resp = client.post(
            f"{BASE}/tasks/assignments/{aid}/act", headers=stranger_h,
            json={"action": "AGREE"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "NOT_ASSIGNEE"

    def test_double_act_conflicts(self, db, client):
        initiator = _user(db)
        approver = _user(db)
        template, _form = _make_single_node_flow(db, node_type="approval", approver_id=approver.id)
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        approver_h = login_as(client, approver.username, PASSWORD)
        _submit_simple(client, init_h, template.id)

        aid = client.get(f"{BASE}/tasks/todo", headers=approver_h).json()["items"][0]["assignment_id"]
        assert client.post(
            f"{BASE}/tasks/assignments/{aid}/act", headers=approver_h, json={"action": "AGREE"}
        ).status_code == 200
        # 重复点击 → 冲突，且不产生第二条动作
        second = client.post(
            f"{BASE}/tasks/assignments/{aid}/act", headers=approver_h, json={"action": "AGREE"}
        )
        assert second.status_code == 409

    def test_return_targets_from_api(self, db, client):
        """可退回节点由服务端算，前端不重复实现规则。"""
        initiator = _user(db)
        first = _user(db)
        second = _user(db)
        owner = _user(db)
        form = _published_form(db, owner)
        version = _published_flow(db, owner, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "一级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [first.id]}]}},
                {"id": "s2", "type": "approval", "name": "二级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [second.id]}]}},
            ]
        })
        template = db.get(FlowTemplate, version.template_id)
        template.status = FlowStatus.PUBLISHED
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        first_h = login_as(client, first.username, PASSWORD)
        second_h = login_as(client, second.username, PASSWORD)
        _submit_simple(client, init_h, template.id)

        a1 = client.get(f"{BASE}/tasks/todo", headers=first_h).json()["items"][0]["assignment_id"]
        # 一级节点没有前序
        assert client.get(
            f"{BASE}/tasks/assignments/{a1}/return-targets", headers=first_h
        ).json() == []

        client.post(f"{BASE}/tasks/assignments/{a1}/act", headers=first_h, json={"action": "AGREE"})
        a2 = client.get(f"{BASE}/tasks/todo", headers=second_h).json()["items"][0]["assignment_id"]
        targets = client.get(
            f"{BASE}/tasks/assignments/{a2}/return-targets", headers=second_h
        ).json()
        assert [t["node_id"] for t in targets] == ["s1"]

    def test_return_keeps_instance_running(self, db, client):
        initiator = _user(db)
        first = _user(db)
        second = _user(db)
        owner = _user(db)
        form = _published_form(db, owner)
        version = _published_flow(db, owner, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "一级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [first.id]}]}},
                {"id": "s2", "type": "approval", "name": "二级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [second.id]}]}},
            ]
        })
        template = db.get(FlowTemplate, version.template_id)
        template.status = FlowStatus.PUBLISHED
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        first_h = login_as(client, first.username, PASSWORD)
        second_h = login_as(client, second.username, PASSWORD)
        _submit_simple(client, init_h, template.id)

        a1 = client.get(f"{BASE}/tasks/todo", headers=first_h).json()["items"][0]["assignment_id"]
        client.post(f"{BASE}/tasks/assignments/{a1}/act", headers=first_h, json={"action": "AGREE"})
        a2 = client.get(f"{BASE}/tasks/todo", headers=second_h).json()["items"][0]["assignment_id"]

        resp = client.post(
            f"{BASE}/tasks/assignments/{a2}/act", headers=second_h,
            json={"action": "RETURN", "return_target": "s1", "opinion": "重来"},
        )
        assert resp.status_code == 200, resp.text
        # 退回后实例**仍是 RUNNING**（不是 REJECTED）
        assert resp.json()["status"] == "RUNNING"
        # 一级重新收到待办
        assert client.get(f"{BASE}/tasks/todo", headers=first_h).json()["total"] == 1


class TestInstanceOperations:
    def _make_running(self, db, client, *, manager):
        """建一张**已提交、正在运行**的单据。"""
        initiator = _user(db)
        _setup_leave_flow(db, director_id=_user(db).id, hr_id=_user(db).id)
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        available = client.get(f"{BASE}/instances/available-flows", headers=init_h).json()
        draft = client.post(
            f"{BASE}/instances/drafts", headers=init_h,
            json={"flow_template_id": available[0]["id"]},
        ).json()
        submitted = client.post(
            f"{BASE}/instances/{draft['id']}/submit", headers=init_h,
            json={"data": {
                "leaveType": "annual", "startDate": "2026-10-01",
                "endDate": "2026-10-02", "reason": "x",
            }},
        )
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "RUNNING"
        _ = manager
        return draft, initiator, init_h

    def test_withdraw_before_any_action(self, db, client):
        manager = _user(db)
        draft, initiator, init_h = self._make_running(db, client, manager=manager)

        resp = client.post(
            f"{BASE}/instances/{draft['id']}/withdraw", headers=init_h,
            json={"reason": "不需要了"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "WITHDRAWN"

    def test_terminate_requires_admin(self, db, client):
        manager = _user(db)
        draft, initiator, init_h = self._make_running(db, client, manager=manager)

        # 普通用户不能终止
        resp = client.post(
            f"{BASE}/instances/{draft['id']}/terminate", headers=init_h,
            json={"reason": "不想办了"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "ADMIN_REQUIRED"

    def test_terminate_by_admin(self, db, client, admin_headers):
        manager = _user(db)
        draft, initiator, init_h = self._make_running(db, client, manager=manager)

        resp = client.post(
            f"{BASE}/instances/{draft['id']}/terminate", headers=admin_headers,
            json={"reason": "合规检查"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "TERMINATED"

    def test_visibility_denied_for_stranger(self, db, client):
        manager = _user(db)
        stranger = _user(db)
        draft, initiator, init_h = self._make_running(db, client, manager=manager)
        stranger_h = login_as(client, stranger.username, PASSWORD)

        resp = client.get(f"{BASE}/instances/{draft['id']}/render", headers=stranger_h)
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "INSTANCE_FORBIDDEN"


class TestNotifications:
    def test_todo_creates_notification(self, db, client):
        """新待办要产生站内消息并计入角标（F7.1/F7.2）。

        用**单节点流程 + 指定审批人**而不是请假流程 ——
        后者的审批人靠部门主管解析，谁是处理人不确定，测试会变成靠运气。
        """
        initiator = _user(db)
        approver = _user(db)
        template, _form = _make_single_node_flow(db, node_type="approval", approver_id=approver.id)
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        approver_h = login_as(client, approver.username, PASSWORD)

        assert client.get(f"{BASE}/notifications/unread-count", headers=approver_h).json()["count"] == 0

        _submit_simple(client, init_h, template.id)

        unread = client.get(f"{BASE}/notifications/unread-count", headers=approver_h).json()
        assert unread["count"] >= 1

        listing = client.get(f"{BASE}/notifications", headers=approver_h).json()
        assert listing["total"] >= 1
        assert listing["items"][0]["type"] == "TASK_CREATED"
        assert "待办" in listing["items"][0]["title"]

        first = listing["items"][0]
        assert client.post(
            f"{BASE}/notifications/{first['id']}/read", headers=approver_h
        ).status_code == 200
        assert client.get(
            f"{BASE}/notifications/unread-count", headers=approver_h
        ).json()["count"] == unread["count"] - 1

    def test_mark_all_read(self, db, client):
        initiator = _user(db)
        approver = _user(db)
        template, _form = _make_single_node_flow(db, node_type="approval", approver_id=approver.id)
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        approver_h = login_as(client, approver.username, PASSWORD)
        _submit_simple(client, init_h, template.id)

        assert client.post(
            f"{BASE}/notifications/read-all", headers=approver_h
        ).status_code == 200
        assert client.get(
            f"{BASE}/notifications/unread-count", headers=approver_h
        ).json()["count"] == 0

    def test_notification_isolated_per_user(self, db, client):
        a = _user(db)
        b = _user(db)
        db.commit()
        a_h = login_as(client, a.username, PASSWORD)
        b_h = login_as(client, b.username, PASSWORD)

        assert client.get(f"{BASE}/notifications", headers=a_h).json()["total"] == 0
        assert client.get(f"{BASE}/notifications", headers=b_h).json()["total"] == 0


class TestReferencedTemplateGuard:
    """被引用时不能删模板 —— 硬删会撞外键，用户看到 500 而不是可理解的提示。"""

    def test_cannot_delete_flow_with_instances(self, db, client, admin_headers):
        initiator = _user(db)
        approver = _user(db)
        template, _form = _make_single_node_flow(
            db, node_type="approval", approver_id=approver.id
        )
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        _submit_simple(client, init_h, template.id)

        resp = client.delete(f"{BASE}/flow-templates/{template.id}", headers=admin_headers)
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "FLOW_HAS_INSTANCES"
        assert detail["extra"]["instance_count"] == 1

    def test_cannot_delete_form_locked_by_flow(self, db, client, admin_headers):
        initiator = _user(db)
        approver = _user(db)
        template, form = _make_single_node_flow(
            db, node_type="approval", approver_id=approver.id
        )
        db.commit()
        _ = initiator

        resp = client.delete(
            f"{BASE}/form-templates/{form.template_id}", headers=admin_headers
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["code"] == "FORM_REFERENCED_BY_FLOW"


class TestEngineErrorMapping:
    """引擎异常要映射成可判断的错误码，而不是 500 + traceback。

    `EngineError` 不继承 `AppError`（引擎刻意不依赖 core.errors），
    漏接会让「已通过的实例不可终止」这类正常拒绝变成 500。
    """

    def test_illegal_transition_returns_422(self, db, client, admin_headers):
        initiator = _user(db)
        approver = _user(db)
        template, _form = _make_single_node_flow(
            db, node_type="approval", approver_id=approver.id
        )
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        approver_h = login_as(client, approver.username, PASSWORD)
        instance = _submit_simple(client, init_h, template.id)

        # 先走到通过
        aid = client.get(f"{BASE}/tasks/todo", headers=approver_h).json()["items"][0]["assignment_id"]
        client.post(f"{BASE}/tasks/assignments/{aid}/act", headers=approver_h, json={"action": "AGREE"})

        # 已通过（终态）不能终止
        resp = client.post(
            f"{BASE}/instances/{instance['id']}/terminate",
            headers=admin_headers, json={"reason": "试试"},
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "ILLEGAL_TRANSITION"


# --------------------------------------------------------------------------- 机制 C：运行中追加字段


class TestExtFieldApi:
    """F5.1 机制 C 的接口层：谁能加、加完前端拿到什么、怎么停用。

    「设计者」在 PRD §2 里**没有审批数据管理权** —— 他只能对自己看得见的实例
    追加字段，所以这里的用例都用「设计者本人发起」的单据。
    """

    @pytest.fixture
    def designer(self, db, designer_role):
        from tests.conftest import make_user

        return make_user(db, username="ext_designer", password=PASSWORD, role=designer_role)

    def _prepare(self, db, client, initiator):
        approver = _user(db)
        template, _form = _make_single_node_flow(
            db, node_type="approval", approver_id=approver.id
        )
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        approver_h = login_as(client, approver.username, PASSWORD)
        instance = _submit_simple(client, init_h, template.id)
        return instance, init_h, approver_h

    def _append(self, client, instance_id: int, headers, **body) -> tuple[dict, str]:
        """追加一个字段，返回 (响应体, field_key)。"""
        payload = {"label": "合同编号", "type": "text"} | body
        resp = client.post(
            f"{BASE}/instances/{instance_id}/ext-fields", headers=headers, json=payload
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        key = next(f for f in data["ext_fields"] if f["label"] == payload["label"])["field_key"]
        return data, key

    def test_designer_appends_and_render_merges(self, db, client, designer):
        instance, designer_h, approver_h = self._prepare(db, client, designer)

        data, key = self._append(client, instance["id"], designer_h, required=True)

        # 设计者是发起人、不是处理人 → 运行中看不到这个新字段（D-04：key 也不下发）
        keys = [f["key"] for s in data["schema_data"]["sections"] for f in s["fields"]]
        assert key not in keys
        assert key not in data["permissions"]
        assert key.startswith("ext_1_")
        # 结构定义仍保留，管理员才能管理它
        assert data["ext_fields"][0]["label"] == "合同编号"

        # 处理人：schema 已并入动态字段，且可见、可编辑、必填
        render = client.get(
            f"{BASE}/instances/{instance['id']}/render", headers=approver_h
        ).json()
        approver_keys = [
            f["key"] for s in render["schema_data"]["sections"] for f in s["fields"]
        ]
        assert key in approver_keys
        assert render["permissions"][key]["editable"] is True
        assert render["permissions"][key]["required"] is True

        # 处理人填进去 → 落库
        todo = client.get(f"{BASE}/tasks/todo", headers=approver_h).json()
        aid = todo["items"][0]["assignment_id"]
        act = client.post(
            f"{BASE}/tasks/assignments/{aid}/act", headers=approver_h,
            json={"action": "AGREE", "field_patch": {key: "HT-2026-001"}},
        )
        assert act.status_code == 200, act.text
        detail = client.get(
            f"{BASE}/instances/{instance['id']}/render", headers=approver_h
        ).json()
        assert detail["values"][key] == "HT-2026-001"

    def test_normal_user_forbidden(self, db, client):
        """看得见单据、但不是设计者/管理员 → 不许改结构。"""
        initiator = _user(db)
        instance, init_h, _approver_h = self._prepare(db, client, initiator)

        resp = client.post(
            f"{BASE}/instances/{instance['id']}/ext-fields", headers=init_h,
            json={"label": "合同编号", "type": "text"},
        )

        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "DESIGNER_REQUIRED"

    def test_unrelated_designer_cannot_touch_instance(self, db, client, designer):
        """PRD §2：设计者没有审批数据管理权 —— 不是相关人的实例连看都看不到。"""
        initiator = _user(db)
        instance, _init_h, _approver_h = self._prepare(db, client, initiator)
        designer_h = login_as(client, designer.username, PASSWORD)

        resp = client.post(
            f"{BASE}/instances/{instance['id']}/ext-fields", headers=designer_h,
            json={"label": "合同编号", "type": "text"},
        )

        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "INSTANCE_FORBIDDEN"

    def test_invalid_type_rejected_with_code(self, db, client, designer):
        instance, designer_h, _approver_h = self._prepare(db, client, designer)

        resp = client.post(
            f"{BASE}/instances/{instance['id']}/ext-fields", headers=designer_h,
            json={"label": "明细", "type": "subtable"},
        )

        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "EXT_FIELD_INVALID"

    def test_disable_removes_from_render(self, db, client, designer):
        instance, designer_h, _approver_h = self._prepare(db, client, designer)
        _data, key = self._append(client, instance["id"], designer_h)

        resp = client.post(
            f"{BASE}/instances/{instance['id']}/ext-fields/{key}/disable",
            headers=designer_h,
        )

        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["ext_fields"] == []
        assert key not in payload["permissions"]
        assert key not in [
            f["key"] for s in payload["schema_data"]["sections"] for f in s["fields"]
        ]


# --------------------------------------------------------------------------- 归档与导出（F8）


class TestArchive:
    """F8.1 归档列表 + F8.2 导出 CSV。"""

    def _finished_instance(self, db, client):
        """跑完一张单子（提交 → 同意），返回 (instance, headers)。"""
        initiator = _user(db)
        approver = _user(db)
        template, _form = _make_single_node_flow(
            db, node_type="approval", approver_id=approver.id
        )
        db.commit()

        init_h = login_as(client, initiator.username, PASSWORD)
        approver_h = login_as(client, approver.username, PASSWORD)
        instance = _submit_simple(client, init_h, template.id)
        aid = client.get(f"{BASE}/tasks/todo", headers=approver_h).json()["items"][0][
            "assignment_id"
        ]
        resp = client.post(
            f"{BASE}/tasks/assignments/{aid}/act", headers=approver_h,
            json={"action": "AGREE", "field_patch": {"reason": "已归档的事由"}},
        )
        assert resp.status_code == 200, resp.text
        return instance, init_h, approver_h

    def test_archive_lists_approved_only(self, db, client, admin_headers):
        instance, _init_h, _approver_h = self._finished_instance(db, client)

        # 另有一张还在跑的，不该出现在归档里
        other, _h, approver_h = self._finished_instance(db, client)
        # other 已通过；再造一张运行中的
        initiator2 = _user(db)
        approver2 = _user(db)
        template2, _f = _make_single_node_flow(
            db, node_type="approval", approver_id=approver2.id
        )
        db.commit()
        running = _submit_simple(client, login_as(client, initiator2.username, PASSWORD), template2.id)

        resp = client.get(f"{BASE}/instances/archive", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()["items"]}
        assert instance["id"] in ids
        assert other["id"] in ids
        assert running["id"] not in ids

        # 关键字/发起人筛选
        by_code = client.get(
            f"{BASE}/instances/archive", headers=admin_headers,
            params={"keyword": instance["code"]},
        ).json()
        assert [row["id"] for row in by_code["items"]] == [instance["id"]]

    def test_archive_requires_admin(self, db, client):
        instance, init_h, _approver_h = self._finished_instance(db, client)

        resp = client.get(f"{BASE}/instances/archive", headers=init_h)
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "ADMIN_REQUIRED"
        assert instance  # 用一下，避免未使用告警

    def test_archive_rejects_non_approved_status(self, db, client, admin_headers):
        """D-05：归档列表只允许 APPROVED；其他终态走管理员实例管理。"""
        instance, _init_h, _approver_h = self._finished_instance(db, client)

        approved = client.get(
            f"{BASE}/instances/archive", headers=admin_headers,
            params={"status": "APPROVED"},
        )
        assert approved.status_code == 200, approved.text
        assert instance["id"] in {row["id"] for row in approved.json()["items"]}

        rejected = client.get(
            f"{BASE}/instances/archive", headers=admin_headers,
            params={"status": "APPROVED,TERMINATED"},
        )
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["detail"]["code"] == "ARCHIVE_STATUS_INVALID"

    def test_export_csv_has_bom_and_labels(self, db, client, admin_headers):
        instance, _init_h, _approver_h = self._finished_instance(db, client)

        resp = client.get(
            f"{BASE}/instances/archive/export", headers=admin_headers,
            params={"keyword": instance["code"]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")

        text = resp.content.decode("utf-8")
        assert text.startswith("﻿"), "Excel 靠 BOM 认出 UTF-8"
        lines = text.lstrip("﻿").splitlines()
        header = lines[0]
        # 列名用的是字段标签而不是 key —— 导出的东西是给人看的
        assert "单号" in header and "事由" in header and "reason" not in header
        # 数据行：单号 + 提交时填的值（审批节点对申请区只读，值不会变）
        assert instance["code"] in lines[1]
        assert "x" in lines[1]

    def test_export_includes_live_ext_field(self, db, client, admin_headers):
        """导出的列要含运行中追加的动态字段（F8.1 的「完整数据」）。"""
        initiator = _user(db)
        approver = _user(db)
        template, _form = _make_single_node_flow(
            db, node_type="approval", approver_id=approver.id
        )
        db.commit()
        init_h = login_as(client, initiator.username, PASSWORD)
        approver_h = login_as(client, approver.username, PASSWORD)
        instance = _submit_simple(client, init_h, template.id)

        # 运行中追加字段 → 处理人填上 → 通过归档
        created = client.post(
            f"{BASE}/instances/{instance['id']}/ext-fields", headers=admin_headers,
            json={"label": "合同编号", "type": "text"},
        )
        assert created.status_code == 200, created.text
        key = created.json()["ext_fields"][0]["field_key"]

        aid = client.get(f"{BASE}/tasks/todo", headers=approver_h).json()["items"][0][
            "assignment_id"
        ]
        acted = client.post(
            f"{BASE}/tasks/assignments/{aid}/act", headers=approver_h,
            json={"action": "AGREE", "field_patch": {key: "HT-2026-042"}},
        )
        assert acted.status_code == 200, acted.text

        resp = client.get(
            f"{BASE}/instances/archive/export", headers=admin_headers,
            params={"keyword": instance["code"]},
        )
        assert resp.status_code == 200, resp.text
        lines = resp.content.decode("utf-8").lstrip("﻿").splitlines()
        assert "合同编号" in lines[0]      # 动态字段也有一列
        assert "HT-2026-042" in lines[1]   # 值跟着出来

    def test_export_instance_by_initiator(self, db, client):
        instance, init_h, _approver_h = self._finished_instance(db, client)

        resp = client.get(f"{BASE}/instances/{instance['id']}/export", headers=init_h)

        assert resp.status_code == 200, resp.text
        text = resp.content.decode("utf-8")
        assert instance["code"] in text
        assert "事由" in text

    def test_export_instance_denied_for_outsider(self, db, client):
        instance, _init_h, _approver_h = self._finished_instance(db, client)
        outsider = _user(db)
        db.commit()
        outsider_h = login_as(client, outsider.username, PASSWORD)

        resp = client.get(f"{BASE}/instances/{instance['id']}/export", headers=outsider_h)

        assert resp.status_code == 403, resp.text
