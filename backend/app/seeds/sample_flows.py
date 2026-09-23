"""示例流程库（M6 ①）。

**为什么需要**：空系统里「发起中心」是空的 —— 试用的人得先自己配一套表单、
再配一套流程、再发布，才能看到这个东西到底能干什么。这里预置请假与报销
两条最常见的流程，配完即可发起、可审批。

**审批人只用内置角色**（部门主管 / 财务 / 平台管理员），不写死具体用户：
- 谁在哪个部门当主管，由组织管理里维护，示例流程跟着走
- 没配主管时引擎会按 `on_empty=to_admin` 转平台管理员并标记异常 ——
  流程照样在跑，只是提示「有人没配」，比卡死强

**幂等**：按名称查重，已存在就整条跳过（不覆盖用户改过的模板）。
创建走的是服务层（`form_service` / `flow_service`），因此和界面上建模板
走同一套校验 —— 示例数据本身也必须发布得出来。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import RoleCode
from app.models import FlowTemplate, FormTemplate, User
from app.services import flow_service, form_service

logger = logging.getLogger(__name__)

#: 示例模板统一的归属分组，便于在列表里一眼分辨
SAMPLE_GROUP = "示例流程库"


# --------------------------------------------------------------------------- 表单


LEAVE_SCHEMA = {
    "sections": [
        {
            "key": "sec_apply", "title": "请假信息", "stage": "apply", "fields": [
                {"key": "leaveType", "label": "假别", "type": "select", "required": True,
                 "options": [{"label": "事假", "value": "personal"},
                             {"label": "年假", "value": "annual"},
                             {"label": "病假", "value": "sick"}]},
                {"key": "startDate", "label": "开始日期", "type": "date", "required": True},
                {"key": "endDate", "label": "结束日期", "type": "date", "required": True},
                {"key": "days", "label": "天数", "type": "formula",
                 "help": "按起止日期自动计算",
                 "formula": {"type": "date_diff", "start_field": "startDate",
                             "end_field": "endDate"}},
                {"key": "reason", "label": "事由", "type": "textarea", "required": True,
                 "validators": {"max_length": 500}},
            ],
        },
    ]
}


REIMBURSE_SCHEMA = {
    "sections": [
        {
            "key": "sec_apply", "title": "报销信息", "stage": "apply", "fields": [
                {"key": "reason", "label": "事由", "type": "text", "required": True},
                {"key": "category", "label": "费用类别", "type": "select", "required": True,
                 "options": [{"label": "差旅", "value": "travel"},
                             {"label": "办公", "value": "office"},
                             {"label": "招待", "value": "guest"}]},
                {"key": "subCategory", "label": "费用明细", "type": "cascader",
                 "help": "选项由「费用类别」决定",
                 "cascader": {"parent_field": "category", "options_by_parent": {
                     "travel": [{"label": "机票", "value": "flight"},
                                {"label": "住宿", "value": "hotel"},
                                {"label": "市内交通", "value": "taxi"}],
                     "office": [{"label": "办公用品", "value": "supply"},
                                {"label": "打印耗材", "value": "print"}],
                     "guest": [{"label": "餐费", "value": "meal"}],
                 }}},
                {"key": "items", "label": "费用明细", "type": "subtable", "required": True,
                 "validators": {"min_rows": 1, "max_rows": 50},
                 "help": "每行填数量与单价，小计自动算",
                 "columns": [
                     {"key": "name", "label": "项目", "type": "text", "required": True},
                     {"key": "qty", "label": "数量", "type": "number", "required": True,
                      "validators": {"min": 0.01}},
                     {"key": "price", "label": "单价", "type": "number", "required": True,
                      "validators": {"min": 0}},
                     {"key": "subtotal", "label": "小计", "type": "formula",
                      "formula": {"type": "arithmetic", "expression": "qty * price"}},
                 ]},
                {"key": "total", "label": "报销总额", "type": "formula",
                 "help": "明细小计之和，超过 2000 元会加签财务复核",
                 "formula": {"type": "subtable_sum", "subtable_key": "items",
                             "column_key": "subtotal"}},
                {"key": "invoice", "label": "发票", "type": "attachment",
                 "validators": {"max_file_count": 10}},
            ],
        },
        {
            "key": "sec_supplement", "title": "财务核销", "stage": "supplement", "fields": [
                {"key": "actualAmount", "label": "实际核销金额", "type": "number",
                 "visible_at_start": False, "validators": {"min": 0}},
                {"key": "invoiceNo", "label": "发票号", "type": "text",
                 "visible_at_start": False, "validators": {"max_length": 64}},
            ],
        },
    ]
}


# --------------------------------------------------------------------------- 流程


def _leave_definition() -> dict:
    return {
        "steps": [
            {"id": "s1", "type": "approval", "name": "直属上级审批",
             "description": "发起人所在部门的主管（组织管理里维护）",
             "assignee": {"mode": "SINGLE",
                          "sources": [{"type": "dept_manager"}]}},
            {"id": "c1", "type": "condition", "name": "按天数分流", "branches": [
                {"id": "long",
                 "when": {"conditions": [{"field": "days", "cmp": ">", "value": 3}]},
                 "steps": [
                     {"id": "s2", "type": "approval", "name": "分管领导审批",
                      "description": "超过 3 天的请假需要更高一级审批",
                      "assignee": {"mode": "SINGLE",
                                   "sources": [{"type": "role",
                                                "role_ids": []}]}},
                 ]},
                {"id": "short", "when": None, "steps": []},
            ]},
        ],
    }


def _reimburse_definition() -> dict:
    return {
        "steps": [
            {"id": "s1", "type": "approval", "name": "部门经理审批",
             "assignee": {"mode": "SINGLE", "sources": [{"type": "dept_manager"}]}},
            {"id": "c1", "type": "condition", "name": "按金额分流", "branches": [
                {"id": "big",
                 "when": {"conditions": [{"field": "total", "cmp": ">", "value": 2000}]},
                 "steps": [
                     {"id": "p1", "type": "parallel", "name": "财务双签", "mode": "all",
                      "description": "会计与财务负责人同时审批，都同意才通过",
                      "members": [
                          {"id": "f1", "type": "approval", "name": "会计审批",
                           "assignee": {"mode": "SINGLE",
                                        "sources": [{"type": "role", "role_ids": []}]}},
                          {"id": "f2", "type": "approval", "name": "财务负责人审批",
                           "assignee": {"mode": "SINGLE",
                                        "sources": [{"type": "role", "role_ids": []}]}},
                      ]},
                 ]},
                {"id": "small", "when": None, "steps": []},
            ]},
            {"id": "s3", "type": "fill", "name": "财务核销",
             "description": "补充实际核销金额与发票号；申请人此时看不到这些字段",
             "fields_permission": {
                 "base": "hidden",
                 "overrides": {"actualAmount": "editable-required", "invoiceNo": "editable"},
             },
             "assignee": {"mode": "SINGLE", "sources": [{"type": "role", "role_ids": []}]}},
            {"id": "cc1", "type": "cc", "name": "抄送财务负责人",
             "cc_to": {"sources": [{"type": "role", "role_ids": []}]}},
        ],
    }


def _role_source(definition: dict, role_ids: dict[str, int]) -> dict:
    """把定义里「占位的角色来源」换成真实角色 id。

    写定义时用空 `role_ids` 占位比硬编码 id 可读 —— id 在不同环境里不一样。
    这里按**节点名**决定该填哪个角色，规则显式列在下面这张表里。
    """
    by_node_name = {
        "分管领导审批": RoleCode.PLATFORM_ADMIN,
        "会计审批": RoleCode.FINANCE,
        "财务负责人审批": RoleCode.PLATFORM_ADMIN,
        "财务核销": RoleCode.FINANCE,
        "抄送财务负责人": RoleCode.FINANCE,
    }

    def fill(rule: dict | None, node_name: str) -> None:
        if not rule:
            return
        code = by_node_name.get(node_name)
        if code is None:
            return
        role_id = role_ids.get(code)
        if role_id is None:
            return
        for source in rule.get("sources", []):
            if source.get("type") == "role" and not source.get("role_ids"):
                source["role_ids"] = [role_id]

    def walk(steps: list[dict]) -> None:
        for step in steps:
            fill(step.get("assignee"), step.get("name", ""))
            fill(step.get("cc_to"), step.get("name", ""))
            for member in step.get("members", []) or []:
                fill(member.get("assignee"), member.get("name", ""))
            for branch in step.get("branches", []) or []:
                walk(branch.get("steps", []) or [])

    walk(definition.get("steps", []))
    return definition


# --------------------------------------------------------------------------- 入口


def _ensure_form(db: Session, actor: User, *, name: str, code: str,
                 description: str, schema: dict) -> FormTemplate:
    existing = db.scalar(select(FormTemplate).where(FormTemplate.name == name))
    if existing is not None:
        return existing

    template = form_service.create_template(
        db,
        form_service.FormTemplateCreate(
            name=name, code=code, group_name=SAMPLE_GROUP,
            description=description, schema_data=schema,
        ),
        actor=actor,
    )
    version = form_service.list_versions(db, template)[0]
    form_service.publish_version(db, version, actor=actor, remark="示例流程库初始化")
    return template


def _ensure_flow(db: Session, actor: User, *, name: str, code: str, description: str,
                 form_template_id: int, definition: dict, role_ids: dict[str, int]):
    existing = db.scalar(select(FlowTemplate).where(FlowTemplate.name == name))
    if existing is not None:
        return existing

    template = flow_service.create_template(
        db,
        name=name, form_template_id=form_template_id, code=code, category=SAMPLE_GROUP,
        description=description, initiator_scope={"type": "all"}, actor=actor,
    )
    version = flow_service.list_versions(db, template)[0]
    flow_service.update_version(
        db, version,
        definition=_role_source(definition, role_ids),
        actor=actor,
    )
    flow_service.publish_version(db, version, remark="示例流程库初始化", actor=actor)
    return template


def run_seed(db: Session, actor: User, *, role_ids: dict[str, int] | None = None) -> None:
    """写入示例流程库。`actor` 是建模板的人（写审计用），通常是初始管理员。"""
    from app.models import Role

    if role_ids is None:
        role_ids = {r.code: r.id for r in db.scalars(select(Role)).all()}

    leave_form = _ensure_form(
        db, actor,
        name="请假申请单", code="SAMPLE_LEAVE_FORM",
        description="示例：假别 / 起止日期 / 天数（公式自动算）/ 事由",
        schema=LEAVE_SCHEMA,
    )
    _ensure_flow(
        db, actor,
        name="请假申请", code="SAMPLE_LEAVE_FLOW",
        description="示例：直属上级审批 →（超过 3 天）分管领导审批",
        form_template_id=leave_form.id,
        definition=_leave_definition(), role_ids=role_ids,
    )

    reimburse_form = _ensure_form(
        db, actor,
        name="费用报销单", code="SAMPLE_REIMBURSE_FORM",
        description="示例：费用明细子表 / 总额公式 / 发票；补充区含实际核销金额",
        schema=REIMBURSE_SCHEMA,
    )
    _ensure_flow(
        db, actor,
        name="费用报销", code="SAMPLE_REIMBURSE_FLOW",
        description="示例：部门经理 →（超过 2000 元）财务双签 → 财务核销 → 抄送财务",
        form_template_id=reimburse_form.id,
        definition=_reimburse_definition(), role_ids=role_ids,
    )

    db.commit()
    logger.info("示例流程库已就绪：请假申请 / 费用报销")
