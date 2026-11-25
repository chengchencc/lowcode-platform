"""发起时自动填充的系统字段（initiator / initiator_dept）。

覆盖：
- schema 校验：只允许顶层且类型匹配的人员/部门控件
- 取值：单选给标量、多选给列表；部门缺失时跳过
- 审批人解析：上一节点=发起人时允许自审（其他来源默认剔除发起人）
- 流程级 `prevent_self_approval` 开关：关闭后角色等宽口径来源也允许发起人
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.engine.approvers import ApproverContext, resolve_approvers
from app.engine.auto_fill import auto_fill_values, default_values
from app.schemas.flow_definition import AssigneeRule, AssigneeSource
from app.schemas.form_schema import parse_form_schema, validate_form_schema


def _schema(*fields: dict[str, Any]) -> Any:
    return parse_form_schema(
        {"sections": [{"key": "sec", "title": "申请", "fields": list(fields)}]}
    )


def _issues(schema: Any) -> list[Any]:
    return validate_form_schema(schema)


def test_auto_fill_accepts_matching_types() -> None:
    schema = _schema(
        {"key": "applicant", "label": "发起人", "type": "user", "auto_fill": "initiator"},
        {"key": "applicants", "label": "发起人(多)", "type": "user_multi", "auto_fill": "initiator"},
        {"key": "dept", "label": "部门", "type": "dept", "auto_fill": "initiator_dept"},
        {"key": "depts", "label": "部门(多)", "type": "dept_multi", "auto_fill": "initiator_dept"},
        {"key": "apply_at", "label": "申请时间", "type": "datetime", "auto_fill": "start_time"},
        {"key": "owner", "label": "负责人", "type": "user", "default_source": "initiator"},
        {"key": "owner_dept", "label": "负责部门", "type": "dept",
         "default_source": "initiator_dept"},
    )
    assert [i for i in _issues(schema) if i.severity == "error"] == []


def test_auto_fill_and_default_conflict() -> None:
    schema = _schema(
        {"key": "owner", "label": "负责人", "type": "user",
         "auto_fill": "initiator", "default_source": "initiator"},
    )
    assert "AUTO_FILL_CONFLICT" in {i.code for i in _issues(schema)}


def test_start_time_requires_datetime() -> None:
    bad = _schema(
        {"key": "apply_at", "label": "申请时间", "type": "text", "auto_fill": "start_time"},
    )
    assert "AUTO_FILL_TYPE" in {i.code for i in _issues(bad)}


def test_auto_fill_rejects_wrong_type_and_subtable_column() -> None:
    wrong = _schema(
        {"key": "text", "label": "文本", "type": "text", "auto_fill": "initiator"},
    )
    codes = {i.code for i in _issues(wrong)}
    assert "AUTO_FILL_TYPE" in codes

    nested = parse_form_schema(
        {
            "sections": [
                {
                    "key": "sec",
                    "title": "申请",
                    "fields": [
                        {
                            "key": "rows",
                            "label": "明细",
                            "type": "subtable",
                            "columns": [
                                {
                                    "key": "owner",
                                    "label": "负责人",
                                    "type": "user",
                                    "auto_fill": "initiator",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )
    assert "AUTO_FILL_SUBTABLE" in {i.code for i in _issues(nested)}


def test_auto_fill_values_scalar_and_list() -> None:
    schema = _schema(
        {"key": "applicant", "label": "发起人", "type": "user", "auto_fill": "initiator"},
        {"key": "applicants", "label": "发起人(多)", "type": "user_multi", "auto_fill": "initiator"},
        {"key": "dept", "label": "部门", "type": "dept", "auto_fill": "initiator_dept"},
        {"key": "depts", "label": "部门(多)", "type": "dept_multi", "auto_fill": "initiator_dept"},
    )
    assert auto_fill_values(schema, user_id=7, dept_id=3) == {
        "applicant": 7,
        "applicants": [7],
        "dept": 3,
        "depts": [3],
    }
    # 没有部门的用户：跳过部门字段，不写空值
    assert auto_fill_values(schema, user_id=7, dept_id=None) == {
        "applicant": 7,
        "applicants": [7],
    }


def test_default_values_are_editable_sources() -> None:
    schema = _schema(
        {"key": "owner", "label": "负责人", "type": "user", "default_source": "initiator"},
        {"key": "owners", "label": "负责人(多)", "type": "user_multi",
         "default_source": "initiator"},
        {"key": "dept", "label": "部门", "type": "dept", "default_source": "initiator_dept"},
    )
    assert default_values(schema, user_id=7, dept_id=3) == {
        "owner": 7, "owners": [7], "dept": 3,
    }


def test_start_time_fills_local_datetime_string() -> None:
    schema = _schema(
        {"key": "apply_at", "label": "申请时间", "type": "datetime",
         "auto_fill": "start_time"},
    )
    assert auto_fill_values(
        schema, user_id=1, dept_id=None, now=datetime(2026, 11, 11, 9, 30, 0)
    ) == {"apply_at": "2026-11-11 09:30:00"}


class _Provider:
    def users_by_ids(self, user_ids: Sequence[int]) -> list[int]:
        return list(user_ids)

    def users_by_role(self, role_ids: Sequence[int]) -> list[int]:
        return [99]


    def dept_manager(self, dept_id: int) -> list[int]:
        return [55]

    def active_user_ids(self, user_ids: Sequence[int]) -> list[int]:
        return list(user_ids)

    def admin_user_ids(self) -> list[int]:
        return [1]

    def current_active_users(self) -> list[int]:
        return [1, 2, 3]


class _SelfRoleProvider(_Provider):
    """角色成员里只有发起人本人 —— 用来验证防自审开关。"""

    def users_by_role(self, role_ids: Sequence[int]) -> list[int]:
        return [1]


def test_prev_node_start_allows_self_approval() -> None:
    rule = AssigneeRule(
        mode="SINGLE",
        sources=[AssigneeSource(type="prev_node_actors", node_id="start")],
    )
    ctx = ApproverContext(initiator_id=1, start_node_id="start")
    resolution = resolve_approvers(rule, ctx, _Provider())
    assert resolution.user_ids == [1]
    assert resolution.abnormal is False


def test_form_user_field_allows_self() -> None:
    """需求负责人默认选发起人时，第一节点应由发起人处理，而不是转管理员。"""
    rule = AssigneeRule(
        mode="SINGLE",
        sources=[AssigneeSource(type="form_user_field", field="req_owner")],
    )
    ctx = ApproverContext(initiator_id=1, start_node_id="start", values={"req_owner": 1})
    resolution = resolve_approvers(rule, ctx, _Provider())
    assert resolution.user_ids == [1]
    assert resolution.abnormal is False


def test_prev_node_real_task_still_excludes_initiator() -> None:
    rule = AssigneeRule(
        mode="SINGLE",
        sources=[AssigneeSource(type="prev_node_actors", node_id="s1")],
    )
    ctx = ApproverContext(
        initiator_id=1,
        start_node_id="start",
        prev_actors={"s1": [1]},
        last_completed_node_id="s1",
    )
    resolution = resolve_approvers(rule, ctx, _Provider())
    # 发起人自己作为上一节点处理人时不应自审 → 无人可派，转管理员并标记异常
    assert resolution.user_ids == []
    assert resolution.abnormal is True


def test_role_source_excludes_initiator_by_default() -> None:
    rule = AssigneeRule(
        mode="SINGLE", sources=[AssigneeSource(type="role", role_ids=[6])]
    )
    ctx = ApproverContext(initiator_id=1, start_node_id="start")
    resolution = resolve_approvers(rule, ctx, _SelfRoleProvider())
    assert resolution.user_ids == []
    assert resolution.abnormal is True


def test_role_source_allows_initiator_when_prevent_disabled() -> None:
    rule = AssigneeRule(
        mode="SINGLE", sources=[AssigneeSource(type="role", role_ids=[6])]
    )
    ctx = ApproverContext(
        initiator_id=1, start_node_id="start", prevent_self_approval=False
    )
    resolution = resolve_approvers(rule, ctx, _SelfRoleProvider())
    assert resolution.user_ids == [1]
    assert resolution.abnormal is False
