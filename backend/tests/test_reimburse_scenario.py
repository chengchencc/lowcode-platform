"""PRD §9 场景二（报销）的端到端走查 —— M5 的验收点。

覆盖：并行会签 + 条件分支 + 子表/公式 + 字段累积（补充区）+ 驳回重提轮次
+ 快照对照 + 机制 C 运行中追加字段 + 抄送。

与 `test_instances_api.py` 的 `TestLeaveScenario` 一样，这里**只走 HTTP 接口** ——
引擎单测已经覆盖了各条语义，这个文件的职责是「真实调用顺序下，一切都还对得上」。
"""

from __future__ import annotations

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

REIMBURSE_SCHEMA = {
    "sections": [
        {
            "key": "sec_apply", "title": "报销信息", "stage": "apply", "fields": [
                {"key": "reason", "label": "事由", "type": "text", "required": True},
                {"key": "category", "label": "费用类别", "type": "select", "required": True,
                 "options": [{"label": "差旅", "value": "travel"},
                             {"label": "办公", "value": "office"}]},
                {"key": "subCategory", "label": "费用明细", "type": "cascader",
                 "cascader": {"parent_field": "category", "options_by_parent": {
                     "travel": [{"label": "机票", "value": "flight"},
                                {"label": "住宿", "value": "hotel"}],
                     "office": [{"label": "打印", "value": "print"}],
                 }}},
                {"key": "items", "label": "费用明细", "type": "subtable", "required": True,
                 "validators": {"min_rows": 1},
                 "columns": [
                     {"key": "name", "label": "项目", "type": "text", "required": True},
                     {"key": "qty", "label": "数量", "type": "number"},
                     {"key": "price", "label": "单价", "type": "number"},
                     {"key": "subtotal", "label": "小计", "type": "formula",
                      "formula": {"type": "arithmetic", "expression": "qty * price"}},
                 ]},
                {"key": "total", "label": "总额", "type": "formula",
                 "formula": {"type": "subtable_sum", "subtable_key": "items",
                             "column_key": "subtotal"}},
            ],
        },
        {
            "key": "sec_supplement", "title": "财务核销", "stage": "supplement", "fields": [
                {"key": "actualAmount", "label": "实际核销金额", "type": "number",
                 "visible_at_start": False},
                {"key": "invoiceNo", "label": "发票号", "type": "text",
                 "visible_at_start": False},
            ],
        },
    ]
}

#: 两张明细，总额 = 2000 * 1 + 1000 * 1 = 3000 > 2000 → 走双签分支
SUBMIT_DATA = {
    "reason": "出差报销",
    "category": "travel",
    "subCategory": "flight",
    "items": [
        {"name": "机票", "qty": 2, "price": 1000},
        {"name": "住宿", "qty": 1, "price": 1000},
    ],
}


def _setup(db, *, manager_id: int, accountant_id: int, cashier_id: int,
           finance_id: int, director_id: int) -> tuple[FlowTemplate, dict]:
    owner = _user(db)
    form = _published_form(db, owner)
    form.schema = REIMBURSE_SCHEMA
    db.flush()

    version = _published_flow(db, owner, form, {
        "steps": [
            {"id": "s1", "type": "approval", "name": "部门经理审批",
             "assignee": {"sources": [{"type": "user", "user_ids": [manager_id]}]}},
            {"id": "c1", "type": "condition", "name": "按总额分流", "branches": [
                {"id": "big",
                 "when": {"conditions": [{"field": "total", "cmp": ">", "value": 2000}]},
                 "steps": [{"id": "p1", "type": "parallel", "name": "财务双签", "mode": "all",
                            "members": [
                                {"id": "f1", "type": "approval", "name": "会计审批",
                                 "assignee": {"sources": [
                                     {"type": "user", "user_ids": [accountant_id]}]}},
                                {"id": "f2", "type": "approval", "name": "出纳审批",
                                 "assignee": {"sources": [
                                     {"type": "user", "user_ids": [cashier_id]}]}},
                            ]}]},
                {"id": "small", "when": None, "steps": []},
            ]},
            {"id": "s3", "type": "fill", "name": "财务核销",
             "fields_permission": {
                 "base": "hidden",
                 "overrides": {"actualAmount": "editable-required", "invoiceNo": "editable"},
             },
             "assignee": {"sources": [{"type": "user", "user_ids": [finance_id]}]}},
            {"id": "cc1", "type": "cc", "name": "抄送财务总监",
             "cc_to": {"sources": [{"type": "user", "user_ids": [director_id]}]}},
        ],
    })
    template = db.get(FlowTemplate, version.template_id)
    assert template is not None
    template.status = FlowStatus.PUBLISHED
    db.flush()

    return template, {}


class TestReimburseScenario:
    """PRD §9 场景二：并行会签 + 字段累积 + 驳回重提 + 机制 C。"""

    def _prepare(self, db, client):
        hq_manager = _user(db)
        accountant = _user(db)
        cashier = _user(db)
        finance = _user(db)
        director = _user(db)
        employee = _user(db)

        template, _ = _setup(
            db, manager_id=hq_manager.id, accountant_id=accountant.id,
            cashier_id=cashier.id, finance_id=finance.id, director_id=director.id,
        )
        db.commit()

        headers = {
            name: login_as(client, user.username, PASSWORD)
            for name, user in [
                ("employee", employee), ("manager", hq_manager), ("accountant", accountant),
                ("cashier", cashier), ("finance", finance), ("director", director),
            ]
        }
        return employee, hq_manager, accountant, cashier, finance, director, template, headers

    # ---- 工具 ----

    def _todo_id(self, client, headers) -> int:
        items = client.get(f"{BASE}/tasks/todo", headers=headers).json()["items"]
        assert items, "应有待办"
        return items[0]["assignment_id"]

    def _act(self, client, headers, assignment_id: int, action: str, **body) -> dict:
        resp = client.post(
            f"{BASE}/tasks/assignments/{assignment_id}/act", headers=headers,
            json={"action": action} | body,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def _render(self, client, headers, instance_id: int) -> dict:
        resp = client.get(f"{BASE}/instances/{instance_id}/render", headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def _submit(self, client, headers, template_id: int, data: dict) -> dict:
        draft = client.post(
            f"{BASE}/instances/drafts", headers=headers,
            json={"flow_template_id": template_id, "title": "出差报销 3000 元"},
        ).json()
        resp = client.post(
            f"{BASE}/instances/{draft['id']}/submit", headers=headers, json={"data": data}
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def _to_finance_node(self, client, headers, instance_id: int) -> None:
        """经理同意 → 双签都同意，把单据推到「财务核销」节点。"""
        self._act(client, headers["manager"], self._todo_id(client, headers["manager"]), "AGREE")
        for who in ("accountant", "cashier"):
            self._act(
                client, headers[who], self._todo_id(client, headers[who]), "AGREE",
                opinion="同意",
            )
        assert instance_id  # 调用方持有；这里只是让签名保持一致

    # ---- ① 并行会签 + 驳回重提 ----

    def test_parallel_reject_then_resubmit(self, db, client):
        (employee, _manager, _accountant, _cashier, _finance, _director,
         template, headers) = self._prepare(db, client)

        instance = self._submit(client, headers["employee"], template.id, SUBMIT_DATA)
        instance_id = instance["id"]

        # 子表与公式：小计逐行算、总额按行小计求和（服务端权威重算）
        render = self._render(client, headers["employee"], instance_id)
        assert render["values"]["total"] == 3000
        assert [row["subtotal"] for row in render["values"]["items"]] == [2000, 1000]
        # D-04：申请阶段补充区字段的 key/标签/值都不下发（不只是 visible=false）
        assert "actualAmount" not in render["permissions"]
        schema_keys = [
            field["key"]
            for section in render["schema_data"]["sections"]
            for field in section["fields"]
        ]
        assert "actualAmount" not in schema_keys
        assert "actualAmount" not in render["values"]

        # 总额 > 2000 → 走双签分支，两人**同时**收到任务
        self._act(client, headers["manager"], self._todo_id(client, headers["manager"]), "AGREE")
        assert client.get(f"{BASE}/tasks/todo", headers=headers["accountant"]).json()["total"] == 1
        assert client.get(f"{BASE}/tasks/todo", headers=headers["cashier"]).json()["total"] == 1

        # 一同意一驳回 → 组失败、整单驳回
        self._act(client, headers["accountant"], self._todo_id(client, headers["accountant"]), "AGREE")
        self._act(
            client, headers["cashier"], self._todo_id(client, headers["cashier"]),
            "REJECT", opinion="发票不全，请补齐",
        )

        render = self._render(client, headers["employee"], instance_id)
        assert render["instance"]["status"] == "REJECTED"
        assert render["instance"]["round"] == 1
        # 发起人能看到驳回意见
        rejected = [a for a in render["actions"] if a["action"] == "REJECT"]
        assert rejected and rejected[-1]["opinion"] == "发票不全，请补齐"
        # 发起人收到驳回通知
        notif = client.get(f"{BASE}/notifications", headers=headers["employee"]).json()
        assert any(n["type"] == "INSTANCE_REJECTED" for n in notif["items"])

        # 改单重提：轮次 +1，流程从头重走
        resp = client.post(
            f"{BASE}/instances/{instance_id}/resubmit", headers=headers["employee"],
            json={"data": {"reason": "出差报销（已补发票）"}, "note": "已补齐发票"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["round"] == 2
        assert resp.json()["status"] == "RUNNING"

        # 经理重新收到待办，且是第二轮
        todo = client.get(f"{BASE}/tasks/todo", headers=headers["manager"]).json()
        assert todo["total"] == 1
        assert todo["items"][0]["round"] == 2

        # 快照对照：两轮提交之间的字段差异
        render = self._render(client, headers["employee"], instance_id)
        submits = [
            a for a in render["actions"]
            if a["action"] in {"SUBMIT", "RESUBMIT"} and a["snapshot_id"]
        ]
        assert len(submits) == 2
        diff_resp = client.get(
            f"{BASE}/instances/{instance_id}/snapshots/diff", headers=headers["employee"],
            params={"from": submits[0]["snapshot_id"], "to": submits[1]["snapshot_id"]},
        )
        assert diff_resp.status_code == 200, diff_resp.text
        diff = diff_resp.json()
        assert any(row["key"] == "reason" for row in diff)

    # ---- ② 字段累积 + 机制 C + 归档可见 ----

    def test_approval_with_supplement_and_live_ext_field(self, db, client, admin_headers):
        (employee, _manager, _accountant, _cashier, finance, director,
         template, headers) = self._prepare(db, client)

        instance = self._submit(client, headers["employee"], template.id, SUBMIT_DATA)
        instance_id = instance["id"]
        self._to_finance_node(client, headers, instance_id)

        # 财务节点：补充字段可编辑且必填；申请人视角仍不可见
        fin_render = self._render(client, headers["finance"], instance_id)
        assert fin_render["current_node"]["name"] == "财务核销"
        assert fin_render["permissions"]["actualAmount"]["editable"] is True
        emp_render = self._render(client, headers["employee"], instance_id)
        assert "actualAmount" not in emp_render["permissions"]

        # 运行中追加「合同编号」：仅当前节点（财务核销）可编辑
        added = client.post(
            f"{BASE}/instances/{instance_id}/ext-fields", headers=admin_headers,
            json={"label": "合同编号", "type": "text", "required": True},
        )
        assert added.status_code == 200, added.text
        payload = added.json()
        ext_key = payload["ext_fields"][0]["field_key"]
        assert ext_key.startswith("ext_")

        # 财务：看得见、可填、必填
        fin_render = self._render(client, headers["finance"], instance_id)
        assert fin_render["permissions"][ext_key]["editable"] is True
        assert fin_render["permissions"][ext_key]["required"] is True
        # 发起人在运行中看不到这个新字段：key 也不应下发
        assert ext_key not in self._render(client, headers["employee"], instance_id)["permissions"]

        fin_task = self._todo_id(client, headers["finance"])
        missing = client.post(
            f"{BASE}/tasks/assignments/{fin_task}/act", headers=headers["finance"],
            json={"action": "SUBMIT", "field_patch": {"actualAmount": 2800}},
        )
        assert missing.status_code == 422, missing.text  # 动态字段标了必填
        assert "合同编号" in missing.json()["detail"]["message"]

        self._act(
            client, headers["finance"], fin_task, "SUBMIT",
            field_patch={"actualAmount": 2800, "invoiceNo": "FP-2026-0001", ext_key: "HT-001"},
        )

        # 通过：抄送财务总监，数据里带上补充字段与动态字段
        final = self._render(client, headers["employee"], instance_id)
        assert final["instance"]["status"] == "APPROVED"
        assert final["values"]["actualAmount"] == 2800
        assert final["values"][ext_key] == "HT-001"
        cc = client.get(f"{BASE}/tasks/cc", headers=headers["director"]).json()
        assert cc["total"] == 1

        # 归档视角：申请人这时才看得到实际核销金额与动态字段（PRD 验收点）
        archived = self._render(client, headers["employee"], instance_id)
        assert archived["permissions"]["actualAmount"]["visible"] is True
        assert archived["permissions"]["actualAmount"]["editable"] is False
        assert archived["permissions"][ext_key]["visible"] is True
        # 动态字段的定义进了快照，历史时点也渲染得出来
        assert any(f["field_key"] == ext_key for f in archived["ext_fields"])
        assert director.id  # 抄送对象用于断言，避免未使用告警
        assert finance.id
