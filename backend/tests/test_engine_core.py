"""引擎纯核心的单测：编译、条件、状态机、令牌推进、聚合、字段权限。

**不需要数据库**（engine 的纯核心不 import db），因此可以穷举语义矩阵。
对应 TECH-DESIGN §4 与 PRD §3.5。
"""

from __future__ import annotations

import pytest

from app.core.constants import AggregateMode, InstanceStatus
from app.engine.aggregate import group_state, next_sequential_seq, node_state
from app.engine.compile import compile_definition
from app.engine.conditions import evaluate_group, pick_branch
from app.engine.errors import EngineError, FlowInvalid, IllegalTransition
from app.engine.machine import (
    EVENT_ABANDON,
    EVENT_FINISH,
    EVENT_REJECT,
    EVENT_RESUBMIT,
    EVENT_SUBMIT,
    EVENT_TERMINATE,
    EVENT_WITHDRAW,
    assert_transition,
    can_transition,
    is_terminal,
)
from app.engine.permissions import (
    ExtFieldView,
    apply_ext_fields,
    column_ref,
    resolve_field_permissions,
    resolve_view_permissions,
)
from app.engine.router import (
    allowed_return_targets,
    cancel_set_for_return,
    plan_after_group,
    plan_after_node,
    plan_start,
)
from app.engine.types import AssignmentView, Cursor, TaskView
from app.schemas.flow_definition import (
    Branch,
    ConditionGroup,
    FieldPermissionRule,
)
from app.schemas.form_schema import parse_form_schema

# --------------------------------------------------------------------------- 测试数据


def _seq(*ids: str, node_type: str = "approval") -> list[dict]:
    return [{"id": i, "type": node_type, "name": i.upper()} for i in ids]


def approval(node_id: str, **extra) -> dict:
    return {"id": node_id, "type": "approval", "name": node_id.upper(), **extra}


def fill(node_id: str, **extra) -> dict:
    return {"id": node_id, "type": "fill", "name": node_id.upper(), **extra}


def cc(node_id: str, **extra) -> dict:
    return {"id": node_id, "type": "cc", "name": node_id.upper(), **extra}


def condition(node_id: str, branches: list[dict], **extra) -> dict:
    return {"id": node_id, "type": "condition", "name": node_id.upper(), "branches": branches, **extra}


def parallel(node_id: str, members: list[dict], mode: str = "all") -> dict:
    return {"id": node_id, "type": "parallel", "name": node_id.upper(), "mode": mode, "members": members}


def flow(steps: list[dict], **extra) -> dict:
    return {"model_version": 1, "steps": steps, **extra}


def _when(field: str, cmp: str, value=None) -> dict:
    """省事的条件组构造。"""
    condition = {"field": field, "cmp": cmp}
    if value is not None:
        condition["value"] = value
    return {"op": "and", "conditions": [condition]}


def cursor(node: str, gates: tuple[str, ...] = ()) -> Cursor:
    return Cursor(node, gates)


def assignment(seq: int, status: str, result: str | None = None) -> AssignmentView:
    return AssignmentView(user_id=seq + 1, status=status, result=result, seq=seq)


def task(node_id: str, status: str, mode: str = "SINGLE") -> TaskView:
    return TaskView(id=hash(node_id) % 1000, node_key=node_id, node_type="APPROVAL",
                    status=status, assignee_mode=mode)


# =========================================================================== 编译


class TestCompile:
    def test_sequential_flow(self):
        compiled = compile_definition(flow([approval("s1"), approval("s2")]))
        assert compiled.root_list == ["s1", "s2"]
        assert compiled.start.type == "start"
        assert compiled.end.type == "end"
        assert compiled.nodes["s1"].placement.kind == "root"
        assert compiled.nodes["s1"].placement.index == 0

    def test_branch_lists_and_gates(self):
        compiled = compile_definition(
            flow([
                condition("c1", [
                    {"id": "b1", "when": _when("n", ">", 10), "steps": [approval("a1"), approval("a2")]},
                    {"id": "b2", "when": None, "steps": [approval("b1")]},
                ]),
                approval("after"),
            ])
        )
        assert compiled.branch_lists[("c1", "b1")] == ["a1", "a2"]
        assert compiled.branch_lists[("c1", "b2")] == ["b1"]
        assert compiled.nodes["a1"].gates == ("c1:b1",)
        assert compiled.nodes["a2"].gates == ("c1:b1",)
        # 条件之后的节点回到顶层，没有 gate
        assert compiled.nodes["after"].gates == ()

    def test_nested_condition_gates_accumulate(self):
        compiled = compile_definition(
            flow([
                condition("c1", [{
                    "id": "b1",
                    "steps": [
                        condition("c2", [{"id": "b2", "steps": [approval("deep")]}]),
                    ],
                }]),
            ])
        )
        assert compiled.nodes["deep"].gates == ("c1:b1", "c2:b2")

    def test_parallel_members(self):
        compiled = compile_definition(
            flow([parallel("p1", [approval("m1"), fill("m2")])])
        )
        assert compiled.parallel_members["p1"] == ["m1", "m2"]
        assert compiled.nodes["m1"].placement.kind == "parallel"
        assert compiled.nodes["m1"].placement.parallel_id == "p1"

    def test_duplicate_node_id_rejected(self):
        with pytest.raises(FlowInvalid, match="重复"):
            compile_definition(flow([approval("s1"), approval("s1")]))

    def test_duplicate_across_levels_rejected(self):
        """跨层同名也要拦 —— 令牌定位依赖 id 全局唯一。"""
        with pytest.raises(FlowInvalid, match="重复"):
            compile_definition(
                flow([
                    approval("s1"),
                    condition("c1", [{"id": "b1", "steps": [approval("s1")]}]),
                ])
            )

    def test_empty_condition_rejected(self):
        with pytest.raises(FlowInvalid, match="没有任何分支"):
            compile_definition(flow([condition("c1", [])]))

    def test_multiple_else_branches_rejected(self):
        with pytest.raises(FlowInvalid, match="多个「否则」"):
            compile_definition(
                flow([condition("c1", [
                    {"id": "b1", "when": None, "steps": []},
                    {"id": "b2", "when": None, "steps": []},
                ])])
            )

    def test_else_must_be_last(self):
        with pytest.raises(FlowInvalid, match="必须排在最后"):
            compile_definition(
                flow([condition("c1", [
                    {"id": "b1", "when": None, "steps": []},
                    {
                        "id": "b2",
                        "when": {"op": "and", "conditions": [{"field": "x", "cmp": "==", "value": 1}]},
                        "steps": [],
                    },
                ])])
            )

    def test_parallel_member_type_restricted(self):
        """并行组内不能放抄送 —— 由 pydantic 的联合类型在解析阶段拦下。

        编译期的同类检查因此不可达，已移除；友好提示由 validate.py 负责（F2.7）。
        """
        with pytest.raises(FlowInvalid):
            compile_definition(flow([parallel("p1", [cc("c1")])]))

    def test_empty_parallel_rejected(self):
        with pytest.raises(FlowInvalid, match="没有任何成员"):
            compile_definition(flow([parallel("p1", [])]))

    def test_start_end_in_middle_rejected(self):
        """StepNode 的联合类型里没有 start/end，pydantic 解析阶段就会拒绝。"""
        with pytest.raises(FlowInvalid):
            compile_definition(flow([{"id": "e", "type": "end", "name": "E"}]))

    def test_id_conflicting_with_start_end(self):
        with pytest.raises(FlowInvalid, match="与发起节点冲突"):
            compile_definition(
                flow([approval("s1")], start={"id": "s1", "type": "start", "name": "发起"})
            )

    def test_single_node_flow_compiles(self):
        compiled = compile_definition(flow([approval("only")]))
        assert compiled.root_list == ["only"]


# =========================================================================== 条件


class TestConditions:
    def _group(self, conditions, op="and") -> ConditionGroup:
        return ConditionGroup.model_validate({"op": op, "conditions": conditions})

    @pytest.mark.parametrize(
        ("cmp", "left", "right", "expected"),
        [
            ("==", 2000, 2000, True),
            ("==", "2000", 2000, True),      # 数字与数字字符串等价
            ("==", 1, 2, False),
            ("!=", 1, 2, True),
            (">", 3000, 2000, True),
            (">", 2000, 2000, False),
            (">=", 2000, 2000, True),
            ("<", 1000, 2000, True),
            ("<=", 2000, 2000, True),
            (">", "2026-09-02", "2026-09-01", True),   # 日期走字典序
            ("in", "a", ["a", "b"], True),
            ("in", "c", ["a", "b"], False),
            ("not_in", "c", ["a", "b"], True),
            ("contains", ["x", "y"], "y", True),
            ("contains", ["x"], "z", False),
            ("is_empty", "", None, True),
            ("is_empty", [], None, True),
            ("is_empty", 0, None, False),
            ("is_not_empty", "x", None, True),
        ],
    )
    def test_comparisons(self, cmp, left, right, expected):
        group = self._group([{"field": "f", "cmp": cmp, "value": right}])
        assert evaluate_group(group, {"f": left}) is expected

    def test_missing_field_is_not_a_match_and_does_not_raise(self):
        """字段还没填时求值条件是常态，绝不能抛错。"""
        group = self._group([{"field": "ghost", "cmp": ">", "value": 1}])
        assert evaluate_group(group, {}) is False

    def test_missing_field_with_is_empty(self):
        group = self._group([{"field": "ghost", "cmp": "is_empty"}])
        assert evaluate_group(group, {}) is True

    def test_and_semantics(self):
        group = self._group([
            {"field": "a", "cmp": ">", "value": 1},
            {"field": "b", "cmp": ">", "value": 1},
        ])
        assert evaluate_group(group, {"a": 2, "b": 2}) is True
        assert evaluate_group(group, {"a": 2, "b": 0}) is False

    def test_or_semantics(self):
        group = self._group([
            {"field": "a", "cmp": ">", "value": 1},
            {"field": "b", "cmp": ">", "value": 1},
        ], op="or")
        assert evaluate_group(group, {"a": 2, "b": 0}) is True
        assert evaluate_group(group, {"a": 0, "b": 0}) is False

    def test_empty_group_semantics(self):
        assert evaluate_group(self._group([]), {}) is True          # and 空组 = 无约束
        assert evaluate_group(self._group([], op="or"), {}) is False

    def test_nested_groups(self):
        group = self._group([
            {"field": "amount", "cmp": ">", "value": 2000},
            {"op": "or", "conditions": [
                {"field": "urgent", "cmp": "==", "value": True},
                {"field": "vip", "cmp": "==", "value": True},
            ]},
        ])
        assert evaluate_group(group, {"amount": 3000, "urgent": True, "vip": False}) is True
        assert evaluate_group(group, {"amount": 3000, "urgent": False, "vip": False}) is False
        assert evaluate_group(group, {"amount": 1000, "urgent": True, "vip": True}) is False

    def test_subtable_column_reference(self):
        group = self._group([{"field": "items[].amount", "cmp": ">", "value": 100}])
        assert evaluate_group(group, {"items": [{"amount": 200}]}) is True
        assert evaluate_group(group, {"items": []}) is False

    def test_pick_branch_order_and_else(self):
        branches = [
            Branch(id="b1", when=ConditionGroup.model_validate(
                {"conditions": [{"field": "n", "cmp": ">", "value": 10}]})),
            Branch(id="b2", when=ConditionGroup.model_validate(
                {"conditions": [{"field": "n", "cmp": ">", "value": 5}]})),
            Branch(id="b3", when=None),
        ]
        assert pick_branch(branches, {"n": 20}).id == "b1"
        assert pick_branch(branches, {"n": 7}).id == "b2"
        assert pick_branch(branches, {"n": 1}).id == "b3"

    def test_pick_branch_without_else_can_miss(self):
        branches = [Branch(id="b1", when=ConditionGroup.model_validate(
            {"conditions": [{"field": "n", "cmp": ">", "value": 10}]}))]
        assert pick_branch(branches, {"n": 1}) is None


# =========================================================================== 状态机


class TestMachine:
    @pytest.mark.parametrize(
        ("current", "event", "expected"),
        [
            (InstanceStatus.DRAFT, EVENT_SUBMIT, InstanceStatus.RUNNING),
            (InstanceStatus.RUNNING, EVENT_FINISH, InstanceStatus.APPROVED),
            (InstanceStatus.RUNNING, EVENT_REJECT, InstanceStatus.REJECTED),
            (InstanceStatus.RUNNING, EVENT_WITHDRAW, InstanceStatus.WITHDRAWN),
            (InstanceStatus.RUNNING, EVENT_TERMINATE, InstanceStatus.TERMINATED),
            (InstanceStatus.REJECTED, EVENT_RESUBMIT, InstanceStatus.RUNNING),
            (InstanceStatus.REJECTED, EVENT_ABANDON, InstanceStatus.WITHDRAWN),
            (InstanceStatus.DRAFT, EVENT_TERMINATE, InstanceStatus.TERMINATED),
        ],
    )
    def test_legal_transitions(self, current, event, expected):
        assert assert_transition(current, event) == expected

    @pytest.mark.parametrize(
        ("current", "event"),
        [
            (InstanceStatus.REJECTED, EVENT_FINISH),      # 驳回后不能直接通过
            (InstanceStatus.DRAFT, EVENT_FINISH),         # 草稿没提交不能通过
            (InstanceStatus.DRAFT, EVENT_REJECT),
            (InstanceStatus.APPROVED, EVENT_REJECT),      # 终态没有出边
            (InstanceStatus.APPROVED, EVENT_WITHDRAW),
            (InstanceStatus.TERMINATED, EVENT_RESUBMIT),
            (InstanceStatus.WITHDRAWN, EVENT_SUBMIT),
        ],
    )
    def test_illegal_transitions_raise(self, current, event):
        with pytest.raises(IllegalTransition):
            assert_transition(current, event)

    def test_terminal_states(self):
        for status in (InstanceStatus.APPROVED, InstanceStatus.WITHDRAWN, InstanceStatus.TERMINATED):
            assert is_terminal(status)
        assert not is_terminal(InstanceStatus.RUNNING)
        assert not is_terminal(InstanceStatus.REJECTED)

    def test_can_transition_matches_table(self):
        assert can_transition(InstanceStatus.RUNNING, EVENT_REJECT)
        assert not can_transition(InstanceStatus.APPROVED, EVENT_REJECT)


# =========================================================================== 令牌推进


class TestRouter:
    def test_plan_start_enters_first_node(self):
        compiled = compile_definition(flow([approval("s1"), approval("s2")]))
        assert plan_start(compiled, {}) == [Cursor("s1")]

    def test_plan_start_empty_flow_goes_to_end(self):
        compiled = compile_definition(flow([]))
        assert plan_start(compiled, {}) == [Cursor("end")]

    def test_sequential_advance(self):
        compiled = compile_definition(flow([approval("s1"), approval("s2")]))
        assert plan_after_node(compiled, cursor("s1"), {}) == [Cursor("s2")]
        assert plan_after_node(compiled, cursor("s2"), {}) == [Cursor("end")]

    def test_condition_picks_matching_branch(self):
        compiled = compile_definition(
            flow([
                condition("c1", [
                    {"id": "hi", "when": {"conditions": [{"field": "n", "cmp": ">", "value": 10}]},
                     "steps": [approval("big")]},
                    {"id": "lo", "when": None, "steps": [approval("small")]},
                ]),
                approval("after"),
            ])
        )
        assert plan_start(compiled, {"n": 20}) == [Cursor("big", ("c1:hi",))]
        assert plan_start(compiled, {"n": 1}) == [Cursor("small", ("c1:lo",))]

    def test_branch_exit_merges_back_to_mainline(self):
        compiled = compile_definition(
            flow([
                condition("c1", [
                    {"id": "b1", "when": _when("n", ">", 10), "steps": [approval("a1")]},
                    {"id": "b2", "when": None, "steps": [approval("b2n")]},
                ]),
                approval("after"),
            ])
        )
        # 分支里的最后一个走完 → 回到条件节点之后的顶层
        assert plan_after_node(compiled, cursor("a1", ("c1:b1",)), {}) == [Cursor("after")]

    def test_multi_node_branch_advances_within_branch(self):
        compiled = compile_definition(
            flow([
                condition("c1", [{"id": "b1", "steps": [approval("a1"), approval("a2")]}]),
                approval("after"),
            ])
        )
        assert plan_after_node(compiled, cursor("a1", ("c1:b1",)), {}) == [
            Cursor("a2", ("c1:b1",))
        ]
        assert plan_after_node(compiled, cursor("a2", ("c1:b1",)), {}) == [Cursor("after")]

    def test_empty_branch_is_skipped(self):
        compiled = compile_definition(
            flow([
                condition("c1", [
                    {"id": "empty", "when": {"conditions": [{"field": "x", "cmp": "==", "value": 1}]},
                     "steps": []},
                    {"id": "else", "when": None, "steps": [approval("other")]},
                ]),
                approval("after"),
            ])
        )
        # 命中空分支 → 直接穿过条件节点
        assert plan_start(compiled, {"x": 1}) == [Cursor("after")]

    def test_condition_without_else_falls_through(self):
        compiled = compile_definition(
            flow([
                condition("c1", [{
                    "id": "b1",
                    "when": {"conditions": [{"field": "x", "cmp": ">", "value": 100}]},
                    "steps": [approval("rare")],
                }]),
                approval("after"),
            ])
        )
        assert plan_start(compiled, {"x": 1}) == [Cursor("after")]
        assert plan_start(compiled, {"x": 999}) == [Cursor("rare", ("c1:b1",))]

    def test_nested_condition_exit_unwinds_correctly(self):
        compiled = compile_definition(
            flow([
                condition("outer", [{
                    "id": "ob",
                    "steps": [
                        condition("inner", [{"id": "ib", "steps": [approval("deep")]}]),
                        approval("afterInner"),
                    ],
                }]),
                approval("tail"),
            ])
        )
        # 内层走完 → 继续外层分支里的下一个节点
        assert plan_after_node(compiled, cursor("deep", ("outer:ob", "inner:ib")), {}) == [
            Cursor("afterInner", ("outer:ob",))
        ]
        # 外层分支最后一个走完 → 回到顶层
        assert plan_after_node(compiled, cursor("afterInner", ("outer:ob",)), {}) == [
            Cursor("tail")
        ]

    def test_parallel_expands_to_all_members(self):
        compiled = compile_definition(
            flow([parallel("p1", [approval("m1"), approval("m2")]), approval("after")])
        )
        assert plan_start(compiled, {}) == [Cursor("m1"), Cursor("m2")]

    def test_parallel_any_also_spawns_all(self):
        """或签也是同时发给所有人，区别在聚合而非派发。"""
        compiled = compile_definition(
            flow([parallel("p1", [approval("m1"), approval("m2")], mode="any")])
        )
        assert plan_start(compiled, {}) == [Cursor("m1"), Cursor("m2")]

    def test_parallel_member_cannot_advance_alone(self):
        compiled = compile_definition(flow([parallel("p1", [approval("m1")])]))
        with pytest.raises(EngineError, match="并行组"):
            plan_after_node(compiled, cursor("m1"), {})

    def test_plan_after_group_continues_mainline(self):
        compiled = compile_definition(
            flow([parallel("p1", [approval("m1")]), approval("after")])
        )
        assert plan_after_group(compiled, cursor("p1"), {}) == [Cursor("after")]

    def test_cc_does_not_block(self):
        """抄送节点派发后主线立即继续 —— 它不占令牌。"""
        compiled = compile_definition(flow([approval("s1"), cc("c1"), approval("s2")]))
        assert plan_after_node(compiled, cursor("s1"), {}) == [Cursor("c1")]

    def test_parallel_inside_condition_branch(self):
        compiled = compile_definition(
            flow([
                condition("c1", [{
                    "id": "b1",
                    "when": {"conditions": [{"field": "big", "cmp": "==", "value": True}]},
                    "steps": [parallel("p1", [approval("m1"), approval("m2")])],
                }]),
                approval("tail"),
            ])
        )
        assert plan_start(compiled, {"big": True}) == [
            Cursor("m1", ("c1:b1",)),
            Cursor("m2", ("c1:b1",)),
        ]
        assert plan_after_group(compiled, Cursor("p1", ("c1:b1",)), {}) == [Cursor("tail")]

    def test_unknown_node_raises(self):
        compiled = compile_definition(flow([approval("s1")]))
        with pytest.raises(FlowInvalid):
            plan_after_node(compiled, cursor("ghost"), {})


# =========================================================================== 退回


class TestReturn:
    def _flow(self):
        return compile_definition(
            flow([approval("s1"), approval("s2"), approval("s3")])
        )

    def test_return_targets_default_to_all_previous(self):
        compiled = self._flow()
        targets = allowed_return_targets(compiled, cursor("s3"))
        assert [t.id for t in targets] == ["s1", "s2"]

    def test_return_targets_exclude_self(self):
        compiled = self._flow()
        assert "s3" not in [t.id for t in allowed_return_targets(compiled, cursor("s3"))]

    def test_return_targets_first_node_has_none(self):
        compiled = self._flow()
        assert allowed_return_targets(compiled, cursor("s1")) == []

    def test_return_targets_whitelist(self):
        compiled = compile_definition(
            flow([approval("s1"), approval("s2"), approval("s3", return_targets=["s1"])])
        )
        assert [t.id for t in allowed_return_targets(compiled, cursor("s3"))] == ["s1"]

    def test_return_targets_empty_means_forbidden(self):
        compiled = compile_definition(
            flow([approval("s1"), approval("s2", return_targets=[])])
        )
        assert allowed_return_targets(compiled, cursor("s2")) == []

    def test_return_targets_exclude_cc_and_condition(self):
        compiled = compile_definition(
            flow([approval("s1"), cc("c1"), condition("cond", [
                {"id": "b", "when": None, "steps": [approval("s2")]},
            ])])
        )
        targets = [t.id for t in allowed_return_targets(compiled, cursor("s2", ("cond:b",)))]
        assert targets == ["s1"]   # 抄送与条件节点都不是可退回目标

    def test_cancel_set_covers_everything_from_target_onwards(self):
        compiled = self._flow()
        pending = [cursor("s2"), cursor("s3")]
        cancelled = cancel_set_for_return(compiled, pending, cursor("s1"))
        assert set(cancelled) == set(pending)

    def test_cancel_set_keeps_strict_ancestors(self):
        """target 的祖先不该被取消（那些位置在它之前）。"""
        compiled = self._flow()
        # 取消的目标 s3，s1 与 s2 是它的祖先 —— 若它们有令牌则保留
        pending = [cursor("s1"), cursor("s2")]
        cancelled = cancel_set_for_return(compiled, pending, cursor("s3"))
        assert cancelled == []

    def test_cancel_set_cancels_target_itself(self):
        compiled = self._flow()
        pending = [cursor("s2"), cursor("s3")]
        cancelled = cancel_set_for_return(compiled, pending, cursor("s2"))
        assert cursor("s2") in cancelled


# =========================================================================== 聚合


class TestAggregate:
    # ---- 节点内 ----

    def test_single_pass_and_fail(self):
        assert node_state(AggregateMode.SINGLE, [assignment(0, "DONE", "AGREE")]) == "DONE"
        assert node_state(AggregateMode.SINGLE, [assignment(0, "DONE", "REJECT")]) == "FAILED"
        assert node_state(AggregateMode.SINGLE, [assignment(0, "PENDING")]) == "OPEN"

    def test_all_requires_everyone(self):
        assert node_state(AggregateMode.ALL, [
            assignment(0, "DONE", "AGREE"), assignment(1, "DONE", "AGREE"),
        ]) == "DONE"
        assert node_state(AggregateMode.ALL, [
            assignment(0, "DONE", "AGREE"), assignment(1, "PENDING"),
        ]) == "OPEN"

    def test_all_fails_on_any_reject(self):
        assert node_state(AggregateMode.ALL, [
            assignment(0, "DONE", "AGREE"), assignment(1, "DONE", "REJECT"),
        ]) == "FAILED"

    def test_all_fails_on_any_return(self):
        assert node_state(AggregateMode.ALL, [
            assignment(0, "DONE", "AGREE"), assignment(1, "DONE", "RETURN"),
        ]) == "FAILED"

    def test_any_passes_on_first_agree(self):
        assert node_state(AggregateMode.ANY, [
            assignment(0, "DONE", "AGREE"), assignment(1, "PENDING"),
        ]) == "DONE"

    def test_any_fails_when_someone_rejects_first(self):
        assert node_state(AggregateMode.ANY, [
            assignment(0, "DONE", "REJECT"), assignment(1, "PENDING"),
        ]) == "FAILED"

    def test_sequential_requires_all(self):
        assert node_state(AggregateMode.SEQUENTIAL, [
            assignment(0, "DONE", "AGREE"), assignment(1, "WAITING", None),
        ]) == "OPEN"
        assert node_state(AggregateMode.SEQUENTIAL, [
            assignment(0, "DONE", "AGREE"), assignment(1, "DONE", "AGREE"),
        ]) == "DONE"

    def test_fill_node_submit_counts_as_pass(self):
        assert node_state(AggregateMode.SINGLE, [assignment(0, "DONE", "SUBMIT")]) == "DONE"

    def test_empty_assignments_is_open(self):
        assert node_state(AggregateMode.ALL, []) == "OPEN"

    # ---- 依次审批的下一个 ----

    def test_next_sequential_seq(self):
        assert next_sequential_seq([
            assignment(0, "DONE", "AGREE"), assignment(1, "WAITING"), assignment(2, "WAITING"),
        ]) == 1
        # 当前还有人待办 → 不激活下一个
        assert next_sequential_seq([
            assignment(0, "PENDING"), assignment(1, "WAITING"),
        ]) is None
        assert next_sequential_seq([assignment(0, "DONE", "AGREE")]) is None

    # ---- 并行组 ----

    def test_group_all_joins_when_everyone_completes(self):
        assert group_state(AggregateMode.ALL, [
            task("m1", "COMPLETED"), task("m2", "COMPLETED"),
        ]) == "JOINED"

    def test_group_all_waits_for_pending(self):
        assert group_state(AggregateMode.ALL, [
            task("m1", "COMPLETED"), task("m2", "PENDING"),
        ]) == "OPEN"

    def test_group_all_fails_on_cancelled(self):
        assert group_state(AggregateMode.ALL, [
            task("m1", "COMPLETED"), task("m2", "CANCELLED"),
        ]) == "FAILED"

    def test_group_any_joins_on_first_complete(self):
        assert group_state(AggregateMode.ANY, [
            task("m1", "COMPLETED"), task("m2", "PENDING"),
        ]) == "JOINED"

    def test_group_any_waits_while_others_still_open(self):
        assert group_state(AggregateMode.ANY, [
            task("m1", "CANCELLED"), task("m2", "PENDING"),
        ]) == "OPEN"

    def test_group_any_fails_when_nobody_left(self):
        assert group_state(AggregateMode.ANY, [
            task("m1", "CANCELLED"), task("m2", "CANCELLED"),
        ]) == "FAILED"

    def test_group_empty_joins(self):
        assert group_state(AggregateMode.ALL, []) == "JOINED"


# =========================================================================== 字段权限


REIMBURSE_FORM = {
    "sections": [
        {
            "key": "sec_apply", "title": "申请信息", "stage": "apply",
            "fields": [
                {"key": "reason", "label": "事由", "type": "text", "required": True},
                {"key": "amount", "label": "金额", "type": "number"},
                {"key": "items", "label": "明细", "type": "subtable", "columns": [
                    {"key": "name", "label": "名称", "type": "text"},
                    {"key": "subtotal", "label": "小计", "type": "formula",
                     "formula": {"type": "arithmetic", "expression": "1 + 1"}},
                ]},
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


class TestPermissions:
    def setup_method(self):
        self.schema = parse_form_schema(REIMBURSE_FORM)

    def _resolve(self, node_type, rule=None, values=None):
        return resolve_field_permissions(
            form_schema=self.schema, node_type=node_type, rule=rule, values=values or {}
        )

    # ---- L0 ----

    def test_start_node_uses_visible_at_start(self):
        perms = self._resolve("start")
        assert perms["reason"].editable is True
        assert perms["amount"].editable is True
        # 补充字段在发起阶段隐藏
        assert perms["actualAmount"].visible is False

    def test_start_node_required_from_template(self):
        perms = self._resolve("start")
        assert perms["reason"].required is True
        assert perms["amount"].required is False

    def test_approval_defaults_apply_readonly_others_hidden(self):
        perms = self._resolve("approval")
        assert perms["reason"].visible is True
        assert perms["reason"].editable is False        # 申请区 → 只读
        assert perms["actualAmount"].visible is False   # 补充区 → 隐藏

    def test_formula_field_never_editable(self):
        perms = self._resolve("start")
        assert perms["items[].subtotal"].editable is False

    # ---- L1 分区批量 ----

    def test_partition_level_rule(self):
        rule = FieldPermissionRule(base="readonly", partitions={"sec_supplement": "editable"})
        perms = self._resolve("fill", rule)
        assert perms["reason"].editable is False
        assert perms["actualAmount"].visible is True
        assert perms["actualAmount"].editable is True

    def test_base_applies_to_unlisted_partitions(self):
        rule = FieldPermissionRule(base="readonly")
        perms = self._resolve("approval", rule)
        assert perms["reason"].visible is True
        assert perms["reason"].editable is False

    # ---- L2 单字段覆盖 ----

    def test_field_override(self):
        rule = FieldPermissionRule(base="hidden", overrides={"reason": "editable"})
        perms = self._resolve("approval", rule)
        assert perms["reason"].editable is True
        assert perms["amount"].visible is False

    def test_override_can_reveal_supplement_field(self):
        """机制 B 的关键：hidden → editable 的反向点亮。"""
        rule = FieldPermissionRule(
            base="hidden",
            overrides={"actualAmount": "editable-required", "reason": "editable"},
        )
        perms = self._resolve("fill", rule)
        assert perms["actualAmount"].visible is True
        assert perms["actualAmount"].editable is True
        assert perms["actualAmount"].required is True

    def test_subtable_column_override(self):
        """子表可见是列可编辑的前提 —— 看不见的表格谈不上改它的列。"""
        rule = FieldPermissionRule(
            base="hidden",
            overrides={"items": "readonly", "items[].name": "editable"},
        )
        perms = self._resolve("approval", rule)
        assert perms["items"].visible is True
        assert perms["items"].editable is False              # 子表本体只读（增删行受控）
        assert perms["items[].name"].editable is True
        assert perms["items[].subtotal"].editable is False   # 公式列仍只读

    def test_column_visibility_follows_subtable(self):
        """子表本体隐藏时，列也应当不可见。"""
        rule = FieldPermissionRule(base="hidden", overrides={"items[].name": "editable"})
        perms = self._resolve("approval", rule)
        assert perms["items"].visible is False
        assert perms["items[].name"].visible is False

    # ---- L3 条件覆盖 ----

    def test_conditional_override(self):
        rule = FieldPermissionRule.model_validate({
            "base": "editable",
            "conditional_overrides": [{
                "when": {"conditions": [{"field": "amount", "cmp": ">", "value": 2000}]},
                "field_key": "amount",
                "mode": "readonly",
            }],
        })
        big = self._resolve("approval", rule, {"amount": 3000})
        small = self._resolve("approval", rule, {"amount": 100})

        assert big["amount"].editable is False
        assert small["amount"].editable is True

    def test_conditional_override_order_first_match_wins(self):
        rule = FieldPermissionRule.model_validate({
            "base": "editable",
            "conditional_overrides": [
                {"when": {"conditions": [{"field": "n", "cmp": ">", "value": 0}]},
                 "field_key": "amount", "mode": "readonly"},
                {"when": {"conditions": [{"field": "n", "cmp": ">", "value": 10}]},
                 "field_key": "amount", "mode": "editable"},
            ],
        })
        perms = self._resolve("approval", rule, {"n": 100})
        assert perms["amount"].editable is False   # 第一条先命中

    # ---- 硬约束 ----

    def test_required_forced_when_editable_and_template_required(self):
        rule = FieldPermissionRule(base="readonly", overrides={"reason": "editable"})
        perms = self._resolve("approval", rule)
        assert perms["reason"].required is True

    def test_formula_not_required_even_if_template_says_so(self):
        schema = parse_form_schema({
            "sections": [{
                "key": "s", "title": "S", "stage": "apply",
                "fields": [{"key": "f", "label": "F", "type": "formula", "required": True,
                            "formula": {"type": "arithmetic", "expression": "1"}}],
            }]
        })
        perms = resolve_field_permissions(form_schema=schema, node_type="start", rule=None)
        assert perms["f"].editable is False
        assert perms["f"].required is False

    # ---- reason 可追溯 ----

    def test_reason_records_which_layer_won(self):
        rule = FieldPermissionRule(base="hidden", overrides={"reason": "editable"})
        perms = self._resolve("approval", rule)
        assert "L2" in perms["reason"].reason
        assert "L1" in perms["amount"].reason

    # ---- 归档视角 ----

    def test_archive_view_reveals_everything_readonly(self):
        """PRD 验收点：申请人全程看不到补充字段，通过后归档可见。"""
        perms = resolve_view_permissions(self.schema)
        assert perms["actualAmount"].visible is True
        assert perms["actualAmount"].editable is False
        assert perms["reason"].visible is True


# =========================================================================== 机制 C（M5 预留）


class TestExtFields:
    def test_ext_field_visible_only_from_target_node(self):
        perms = {}
        ext = ExtFieldView(
            field_key="contractNo", label="合同编号", type="text",
            editable_node_ids=("s3",), visible_from_node_id="s3",
        )
        # s1 是 s3 之前的节点 → 不可见
        apply_ext_fields(perms, [ext], node_id="s1", node_ancestors=["s1"])
        assert perms["contractNo"].visible is False

        # s3 自身 → 可编辑
        apply_ext_fields(perms, [ext], node_id="s3", node_ancestors=["s1", "s2", "s3"])
        assert perms["contractNo"].editable is True

        # s4 在 s3 之后 → 可见但只读
        apply_ext_fields(perms, [ext], node_id="s4", node_ancestors=["s1", "s2", "s3", "s4"])
        assert perms["contractNo"].visible is True
        assert perms["contractNo"].editable is False

    def test_disabled_ext_field_disappears(self):
        perms = {}
        ext = ExtFieldView(field_key="x", label="X", type="text", active=False)
        apply_ext_fields(perms, [ext], node_id="s1", node_ancestors=["s1"])
        assert "x" not in perms


def test_column_ref_notation_is_stable():
    """列引用记法是权限矩阵与字段 diff 共用的，改动会波及多处。"""
    assert column_ref("items", "amount") == "items[].amount"
