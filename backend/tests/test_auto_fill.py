"""发起时自动填充的系统字段（initiator / initiator_dept）。

覆盖：
- schema 校验：只允许顶层且类型匹配的人员/部门控件
- 取值：单选给标量、多选给列表；部门缺失时跳过
- 审批人解析：上一节点=发起人时允许自审（其他来源仍剔除发起人）
"""

from __future__ import annotations

from typing import Any, Sequence

from app.engine.approvers import ApproverContext, resolve_approvers
from app.engine.auto_fill import auto_fill_values
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
    )
    assert [i for i in _issues(schema) if i.severity == "error"] == []


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


def test_prev_node_start_allows_self_approval() -> None:
    rule = AssigneeRule(
        mode="SINGLE",
        sources=[AssigneeSource(type="prev_node_actors", node_id="start")],
    )
    ctx = ApproverContext(initiator_id=1, start_node_id="start")
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
