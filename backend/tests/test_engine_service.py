"""引擎编排层的集成测试（真实库）。

对应 PRD §3.5 的语义矩阵与 TECH-DESIGN §4.3 的事件表。
纯核心的语义已在 `test_engine_core.py` 覆盖，这里验证的是
「令牌操作 → 落库 → 状态投影」这条链路真的对。
"""

from __future__ import annotations

import itertools

import pytest
from sqlalchemy import func, select

from app.core.constants import (
    AssignmentStatus,
    InstanceStatus,
    TaskStatus,
    UserStatus,
)
from app.core.errors import AppError
from app.core.security import hash_password
from app.engine.errors import IllegalTransition
from app.engine.ext_fields import ExtFieldError, ExtFieldSpec
from app.engine.service import EngineService
from app.models import (
    DataSnapshot,
    Department,
    FlowInstance,
    FlowTemplate,
    FlowVersion,
    FormTemplate,
    FormVersion,
    InstanceAction,
    Notification,
    Task,
    TaskAssignment,
    User,
)
from app.schemas.flow_definition import FlowDefinition
from app.services.approver_provider import DbApproverProvider

_counter = itertools.count(1)

#: 测试用户的统一密码。由 test_instances_api 复用登录。
FACTORY_PASSWORD = "pass123456"

FORM_SCHEMA = {
    "sections": [
        {
            "key": "sec_apply",
            "title": "申请信息",
            "stage": "apply",
            "fields": [
                {"key": "reason", "label": "事由", "type": "text", "required": True},
                {"key": "amount", "label": "金额", "type": "number"},
                {"key": "days", "label": "天数", "type": "number"},
            ],
        },
        {
            "key": "sec_supplement",
            "title": "补充",
            "stage": "supplement",
            "fields": [
                {"key": "actualAmount", "label": "实际核销", "type": "number",
                 "visible_at_start": False},
            ],
        },
    ]
}


# --------------------------------------------------------------------------- 夹具


def _user(db, name: str | None = None, *, dept_id: int | None = None) -> User:
    n = next(_counter)
    user = User(
        username=f"{name or 'u'}{n}",
        real_name=f"用户{n}",
        password_hash=hash_password(FACTORY_PASSWORD),
        status=UserStatus.ACTIVE,
        dept_id=dept_id,
    )
    db.add(user)
    db.flush()
    return user


def _published_form(db, actor: User) -> FormVersion:
    from app.core.constants import FormStatus, FormVersionStatus

    template = FormTemplate(
        name=f"表单{next(_counter)}", status=FormStatus.PUBLISHED, created_by=actor.id
    )
    db.add(template)
    db.flush()
    version = FormVersion(
        template_id=template.id, version_no=1, schema=FORM_SCHEMA,
        status=FormVersionStatus.PUBLISHED, created_by=actor.id,
    )
    db.add(version)
    db.flush()
    template.current_version_id = version.id
    db.flush()
    return version


def _published_form_with(db, actor: User, schema: dict) -> FormVersion:
    """指定 schema 的已发布表单版本（自动填充等用例需要自定义字段）。"""
    from app.core.constants import FormStatus, FormVersionStatus

    template = FormTemplate(
        name=f"表单{next(_counter)}", status=FormStatus.PUBLISHED, created_by=actor.id
    )
    db.add(template)
    db.flush()
    version = FormVersion(
        template_id=template.id, version_no=1, schema=schema,
        status=FormVersionStatus.PUBLISHED, created_by=actor.id,
    )
    db.add(version)
    db.flush()
    template.current_version_id = version.id
    db.flush()
    return version


def _published_flow(db, actor: User, form_version: FormVersion, definition: dict) -> FlowVersion:
    from app.core.constants import FlowStatus, FlowVersionStatus

    template = FlowTemplate(
        name=f"流程{next(_counter)}", form_template_id=form_version.template_id,
        status=FlowStatus.PUBLISHED, initiator_scope={"type": "all"}, created_by=actor.id,
    )
    db.add(template)
    db.flush()
    parsed = FlowDefinition.model_validate(definition)
    version = FlowVersion(
        template_id=template.id, version_no=1,
        definition=parsed.model_dump(mode="json"),
        locked_form_version_id=form_version.id,
        status=FlowVersionStatus.PUBLISHED, created_by=actor.id,
    )
    db.add(version)
    db.flush()
    template.current_version_id = version.id
    db.flush()
    return version


def _draft_instance(
    db, flow_version: FlowVersion, form_version: FormVersion, initiator: User, **data
) -> FlowInstance:
    instance = FlowInstance(
        code=f"T{next(_counter):08d}",
        flow_template_id=flow_version.template_id,
        flow_version_id=flow_version.id,
        form_version_id=form_version.id,
        title="测试单据",
        initiator_id=initiator.id,
        initiator_dept_id=initiator.dept_id,
        status=InstanceStatus.DRAFT,
        data_schema={},
        current_data=dict(data),
    )
    db.add(instance)
    db.flush()
    return instance


def _engine(db) -> EngineService:
    return EngineService(db, provider=DbApproverProvider(db))


def _superusers(db) -> list[User]:
    return list(db.scalars(select(User).where(User.is_superuser.is_(True))).all())


def _blocking_pending(db, instance_id: int) -> list[Task]:
    """活跃令牌 = 待办 且 阻塞主线。抄送不算。"""
    return [t for t in _pending_tasks(db, instance_id) if t.blocks_flow]


def _pending_tasks(db, instance_id: int) -> list[Task]:
    return list(
        db.scalars(
            select(Task).where(
                Task.instance_id == instance_id, Task.status == TaskStatus.PENDING
            ).order_by(Task.id)
        ).all()
    )


def _pending_assignments(db, instance_id: int) -> list[TaskAssignment]:
    return list(
        db.scalars(
            select(TaskAssignment).where(
                TaskAssignment.instance_id == instance_id,
                TaskAssignment.status == AssignmentStatus.PENDING,
            ).order_by(TaskAssignment.id)
        ).all()
    )


def _assignment_of(db, instance_id: int, user: User) -> TaskAssignment:
    row = db.scalar(
        select(TaskAssignment).where(
            TaskAssignment.instance_id == instance_id,
            TaskAssignment.user_id == user.id,
            TaskAssignment.status == AssignmentStatus.PENDING,
        )
    )
    assert row is not None, f"用户 {user.id} 没有待办"
    return row


# --------------------------------------------------------------------------- 提交


class TestSubmit:
    def test_submit_dispatches_first_node(self, db):
        admin = _user(db)
        approver = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{
                "id": "s1", "type": "approval", "name": "经理审批",
                "assignee": {"mode": "SINGLE", "sources": [{"type": "user", "user_ids": [approver.id]}]},
            }],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        result = _engine(db).submit(instance=instance, actor=admin, data={"reason": "出差"})

        assert result.instance_status == InstanceStatus.RUNNING
        assert instance.started_at is not None
        pending = _pending_tasks(db, instance.id)
        assert len(pending) == 1
        assert pending[0].node_key == "s1"
        assert instance.current_node_keys == ["经理审批"]
        # 审批人收到待办通知
        notif = db.scalar(
            select(Notification).where(Notification.user_id == approver.id)
        )
        assert notif is not None and notif.type == "TASK_CREATED"

    def test_submit_auto_fills_initiator_and_dept(self, db):
        dept = Department(code=f"D{next(_counter)}", name="测试部门")
        db.add(dept)
        db.flush()
        admin = _user(db, dept_id=dept.id)
        approver = _user(db)
        form = _published_form_with(db, admin, {
            "sections": [{
                "key": "sec", "title": "申请", "fields": [
                    {"key": "applicant", "label": "发起人", "type": "user",
                     "auto_fill": "initiator"},
                    {"key": "applyDept", "label": "发起部门", "type": "dept",
                     "auto_fill": "initiator_dept"},
                    {"key": "applyAt", "label": "申请时间", "type": "datetime",
                     "auto_fill": "start_time"},
                    {"key": "owner", "label": "需求负责人", "type": "user",
                     "default_source": "initiator"},
                    {"key": "reason", "label": "事由", "type": "text"},
                ],
            }],
        })
        flow = _published_flow(db, admin, form, {
            "steps": [{
                "id": "s1", "type": "approval", "name": "审批",
                "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]},
            }],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        # 客户端传的错误值必须被服务端的自动填充覆盖
        _engine(db).submit(
            instance=instance, actor=admin,
            data={"applicant": 99999, "applyDept": 99999, "reason": "x"},
        )

        assert instance.current_data["applicant"] == admin.id
        assert instance.current_data["applyDept"] == dept.id
        # 可修改的默认值：发起人没填时带入本人
        assert instance.current_data["owner"] == admin.id
        # 发起时间由服务端写入本地时间字符串
        assert isinstance(instance.current_data["applyAt"], str)
        assert len(instance.current_data["applyAt"]) == 19

    def test_submit_requires_required_fields(self, db):
        admin = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{"id": "s1", "type": "approval", "name": "A",
                       "assignee": {"sources": [{"type": "user", "user_ids": [admin.id]}]}}],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        with pytest.raises(AppError, match="必填"):
            _engine(db).submit(instance=instance, actor=admin, data={})

    def test_submit_writes_snapshot_and_action(self, db):
        admin = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {"steps": []})
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        result = _engine(db).submit(instance=instance, actor=admin, data={"reason": "x"})
        assert result.action_id is not None
        assert result.snapshot_id is not None

        snaps = list(
            db.scalars(
                select(DataSnapshot)
                .where(DataSnapshot.instance_id == instance.id)
                .order_by(DataSnapshot.seq)
            ).all()
        )
        # 空流程会立刻走到结束：提交快照 + 归档快照 各一条
        assert [s.kind for s in snaps] == ["SUBMIT", "ARCHIVE"]
        assert snaps[0].data["values"]["reason"] == "x"
        assert snaps[0].seq == 1 and snaps[1].seq == 2

    def test_empty_flow_finishes_immediately(self, db):
        admin = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {"steps": []})
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        result = _engine(db).submit(instance=instance, actor=admin, data={"reason": "x"})
        assert result.instance_status == InstanceStatus.APPROVED
        assert instance.finished_at is not None

    def test_double_submit_rejected(self, db):
        admin = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {"steps": []})
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        with pytest.raises(IllegalTransition):
            engine.submit(instance=instance, actor=admin, data={"reason": "y"})


# --------------------------------------------------------------------------- 条件分支


class TestCondition:
    def _build(self, db):
        admin = _user(db)
        big = _user(db)
        small = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{
                "id": "c1", "type": "condition", "name": "按金额分流",
                "branches": [
                    {"id": "big", "when": {"conditions": [{"field": "amount", "cmp": ">", "value": 2000}]},
                     "steps": [{"id": "sBig", "type": "approval", "name": "总监审批",
                                "assignee": {"sources": [{"type": "user", "user_ids": [big.id]}]}}]},
                    {"id": "small", "when": None,
                     "steps": [{"id": "sSmall", "type": "approval", "name": "经理审批",
                                "assignee": {"sources": [{"type": "user", "user_ids": [small.id]}]}}]},
                ],
            }],
        })
        return admin, big, small, form, flow

    def test_big_amount_goes_to_director(self, db):
        admin, big, small, form, flow = self._build(db)
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        _engine(db).submit(instance=instance, actor=admin, data={"reason": "x", "amount": 5000})

        tasks = _pending_tasks(db, instance.id)
        assert [t.node_key for t in tasks] == ["sBig"]
        assert tasks[0].gates == ["c1:big"]

    def test_small_amount_goes_to_manager(self, db):
        admin, big, small, form, flow = self._build(db)
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        _engine(db).submit(instance=instance, actor=admin, data={"reason": "x", "amount": 100})

        tasks = _pending_tasks(db, instance.id)
        assert [t.node_key for t in tasks] == ["sSmall"]
        assert tasks[0].gates == ["c1:small"]

    def test_branch_exit_continues_mainline(self, db):
        admin, big, small, form, flow = self._build(db)
        tail = _user(db)
        definition = FlowDefinition.model_validate(flow.definition)
        definition.steps.append(
            FlowDefinition.model_validate({
                "steps": [{"id": "tail", "type": "approval", "name": "收尾",
                           "assignee": {"sources": [{"type": "user", "user_ids": [tail.id]}]}}]
            }).steps[0]
        )
        flow.definition = definition.model_dump(mode="json")
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x", "amount": 100})
        engine.act(assignment_id=_assignment_of(db, instance.id, small).id, actor=small, action="AGREE")

        tasks = _pending_tasks(db, instance.id)
        assert [t.node_key for t in tasks] == ["tail"]
        # 分支走完后 gates 应回到顶层
        assert tasks[0].gates == []


# --------------------------------------------------------------------------- 会签 / 或签


class TestAggregation:
    def _build_parallel(self, db, mode: str):
        admin = _user(db)
        a, b = _user(db), _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{
                "id": "p1", "type": "parallel", "name": "财务双签", "mode": mode,
                "members": [
                    {"id": "m1", "type": "approval", "name": "会计审批",
                     "assignee": {"sources": [{"type": "user", "user_ids": [a.id]}]}},
                    {"id": "m2", "type": "approval", "name": "复核审批",
                     "assignee": {"sources": [{"type": "user", "user_ids": [b.id]}]}},
                ],
            }],
        })
        return admin, a, b, form, flow

    def test_parallel_all_both_agree(self, db):
        admin, a, b, form, flow = self._build_parallel(db, "all")
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})

        tasks = _pending_tasks(db, instance.id)
        assert sorted(t.node_key for t in tasks) == ["m1", "m2"]
        assert tasks[0].group_id and tasks[0].group_id == tasks[1].group_id

        engine.act(assignment_id=_assignment_of(db, instance.id, a).id, actor=a, action="AGREE")
        # 还差一个 → 仍是 RUNNING，还有待办
        assert instance.status == InstanceStatus.RUNNING
        assert len(_pending_tasks(db, instance.id)) == 1

        engine.act(assignment_id=_assignment_of(db, instance.id, b).id, actor=b, action="AGREE")
        assert instance.status == InstanceStatus.APPROVED

    def test_parallel_all_one_rejects_fails_whole_instance(self, db):
        admin, a, b, form, flow = self._build_parallel(db, "all")
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        engine.act(
            assignment_id=_assignment_of(db, instance.id, a).id, actor=a,
            action="REJECT", opinion="金额不对",
        )

        assert instance.status == InstanceStatus.REJECTED
        # 组内其余成员的任务被取消
        assert _pending_tasks(db, instance.id) == []
        b_assignment = db.scalar(
            select(TaskAssignment).where(
                TaskAssignment.instance_id == instance.id, TaskAssignment.user_id == b.id
            )
        )
        assert b_assignment is not None
        assert b_assignment.status == AssignmentStatus.CANCELLED

    def test_parallel_any_first_agree_joins(self, db):
        admin, a, b, form, flow = self._build_parallel(db, "any")
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        engine.act(assignment_id=_assignment_of(db, instance.id, a).id, actor=a, action="AGREE")

        assert instance.status == InstanceStatus.APPROVED
        b_assignment = db.scalar(
            select(TaskAssignment).where(
                TaskAssignment.instance_id == instance.id, TaskAssignment.user_id == b.id
            )
        )
        assert b_assignment.status == AssignmentStatus.CANCELLED

    def test_node_all_sign_mode(self, db):
        """同一节点内的会签（一个 task + N 个 assignment）。"""
        admin = _user(db)
        a, b = _user(db), _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{
                "id": "s1", "type": "approval", "name": "双人会签",
                "assignee": {"mode": "ALL",
                             "sources": [{"type": "user", "user_ids": [a.id, b.id]}]},
            }],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        assert len(_pending_tasks(db, instance.id)) == 1     # 一个节点一个令牌

        engine.act(assignment_id=_assignment_of(db, instance.id, a).id, actor=a, action="AGREE")
        assert instance.status == InstanceStatus.RUNNING

        engine.act(assignment_id=_assignment_of(db, instance.id, b).id, actor=b, action="AGREE")
        assert instance.status == InstanceStatus.APPROVED

    def test_node_any_sign_cancels_siblings(self, db):
        admin = _user(db)
        a, b = _user(db), _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{
                "id": "s1", "type": "approval", "name": "或签",
                "assignee": {"mode": "ANY",
                             "sources": [{"type": "user", "user_ids": [a.id, b.id]}]},
            }],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        engine.act(assignment_id=_assignment_of(db, instance.id, a).id, actor=a, action="AGREE")

        assert instance.status == InstanceStatus.APPROVED
        b_assignment = db.scalar(
            select(TaskAssignment).where(
                TaskAssignment.instance_id == instance.id, TaskAssignment.user_id == b.id
            )
        )
        assert b_assignment.status == AssignmentStatus.CANCELLED
        assert b_assignment.cancel_reason == "ANY_SIGN_DONE"

    def test_sequential_activates_one_at_a_time(self, db):
        admin = _user(db)
        a, b = _user(db), _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{
                "id": "s1", "type": "approval", "name": "依次审批",
                "assignee": {"mode": "SEQUENTIAL",
                             "sources": [{"type": "user", "user_ids": [a.id, b.id]}]},
            }],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})

        rows = {
            r.user_id: r.status
            for r in db.scalars(
                select(TaskAssignment).where(TaskAssignment.instance_id == instance.id)
            ).all()
        }
        assert rows[a.id] == AssignmentStatus.PENDING
        assert rows[b.id] == AssignmentStatus.WAITING   # 依次：第二个人还没轮到

        engine.act(assignment_id=_assignment_of(db, instance.id, a).id, actor=a, action="AGREE")
        db.refresh(db.scalar(select(TaskAssignment).where(
            TaskAssignment.instance_id == instance.id, TaskAssignment.user_id == b.id)))
        assert instance.status == InstanceStatus.RUNNING


# --------------------------------------------------------------------------- 驳回 / 重提


class TestRejectAndResubmit:
    def _build(self, db):
        admin = _user(db)
        manager = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "经理审批",
                 "assignee": {"sources": [{"type": "user", "user_ids": [manager.id]}]}},
                {"id": "s2", "type": "approval", "name": "总监审批",
                 "assignee": {"sources": [{"type": "user", "user_ids": [admin.id]}]}},
            ],
        })
        return admin, manager, form, flow

    def test_reject_then_resubmit_restarts_from_beginning(self, db):
        admin, manager, form, flow = self._build(db)
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "首轮"})

        engine.act(
            assignment_id=_assignment_of(db, instance.id, manager).id,
            actor=manager, action="REJECT", opinion="事由不清",
        )
        assert instance.status == InstanceStatus.REJECTED
        assert _pending_tasks(db, instance.id) == []

        # 驳回意见要能回传给发起人
        snap = db.scalars(
            select(DataSnapshot).where(DataSnapshot.instance_id == instance.id)
            .order_by(DataSnapshot.seq.desc())
        ).first()
        assert snap is not None

        engine.resubmit(instance=instance, actor=admin, data={"reason": "改过了"})
        assert instance.status == InstanceStatus.RUNNING
        assert instance.round == 2
        # 从头重走：经理的待办重新出现
        tasks = _pending_tasks(db, instance.id)
        assert [t.node_key for t in tasks] == ["s1"]
        assert tasks[0].round == 2

    def test_old_round_tasks_are_stale(self, db):
        admin, manager, form, flow = self._build(db)
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        first = _assignment_of(db, instance.id, manager)
        engine.act(assignment_id=first.id, actor=manager, action="REJECT", opinion="no")
        engine.resubmit(instance=instance, actor=admin, data={"reason": "y"})

        # 驳回者自己的 assignment 是 DONE（动作已完成），但它所属的 task 已作废
        db.refresh(first)
        assert first.status == AssignmentStatus.DONE
        assert first.task is not None and first.task.status == TaskStatus.CANCELLED

        # 上一轮的 task 不能再处理
        with pytest.raises(AppError):
            engine.act(assignment_id=first.id, actor=manager, action="AGREE")

    def test_reject_requires_opinion(self, db):
        admin, manager, form, flow = self._build(db)
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        with pytest.raises(AppError, match="驳回必须填写意见"):
            engine.act(
                assignment_id=_assignment_of(db, instance.id, manager).id,
                actor=manager, action="REJECT",
            )


# --------------------------------------------------------------------------- 退回


class TestReturn:
    def _build(self, db):
        admin = _user(db)
        first, second, third = _user(db), _user(db), _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "一级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [first.id]}]}},
                {"id": "s2", "type": "approval", "name": "二级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [second.id]}]}},
                {"id": "s3", "type": "approval", "name": "三级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [third.id]}]}},
            ],
        })
        return admin, first, second, third, form, flow

    def test_return_keeps_running_and_redispatches_target(self, db):
        admin, first, second, third, form, flow = self._build(db)
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x", "amount": 100})

        engine.act(assignment_id=_assignment_of(db, instance.id, first).id, actor=first, action="AGREE")
        engine.act(assignment_id=_assignment_of(db, instance.id, second).id, actor=second, action="AGREE")
        assert len(_pending_tasks(db, instance.id)) == 1

        # 三级退回一级
        engine.act(
            assignment_id=_assignment_of(db, instance.id, third).id,
            actor=third, action="RETURN", return_target="s1", opinion="重新核对",
        )

        # **实例仍 RUNNING**（不是 REJECTED）
        assert instance.status == InstanceStatus.RUNNING
        # 一级重新派发，activation_seq 递增（历史任务保留）
        tasks = _pending_tasks(db, instance.id)
        assert [t.node_key for t in tasks] == ["s1"]
        assert tasks[0].activation_seq == 2
        # 一级的第一次任务仍是 COMPLETED
        first_task = db.scalar(
            select(Task).where(
                Task.instance_id == instance.id, Task.node_key == "s1", Task.activation_seq == 1
            )
        )
        assert first_task is not None and first_task.status == TaskStatus.COMPLETED

    def test_return_does_not_rollback_data(self, db):
        """PRD §3.5.4：退回后**字段数据保留**，不回滚。

        二级节点要能改 amount，所以给它配 editable ——
        默认情况下申请区在审批节点是只读的。
        """
        initiator = _user(db)
        first, second, third = _user(db), _user(db), _user(db)
        form = _published_form(db, initiator)
        flow = _published_flow(db, initiator, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "一级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [first.id]}]}},
                {"id": "s2", "type": "approval", "name": "二级",
                 "fields_permission": {"base": "hidden", "overrides": {"amount": "editable"}},
                 "assignee": {"sources": [{"type": "user", "user_ids": [second.id]}]}},
                {"id": "s3", "type": "approval", "name": "三级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [third.id]}]}},
            ],
        })
        instance = _draft_instance(db, flow, form, initiator)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=initiator, data={"reason": "初始"})

        engine.act(assignment_id=_assignment_of(db, instance.id, first).id, actor=first, action="AGREE")
        engine.act(
            assignment_id=_assignment_of(db, instance.id, second).id, actor=second,
            action="AGREE", field_patch={"amount": 999},
        )
        assert instance.current_data["amount"] == 999

        engine.act(
            assignment_id=_assignment_of(db, instance.id, third).id,
            actor=third, action="RETURN", return_target="s1", opinion="重来",
        )

        # 字段数据**不回滚**
        assert instance.current_data["amount"] == 999
        assert instance.status == InstanceStatus.RUNNING

    def test_return_target_must_be_ancestor(self, db):
        admin, first, second, third, form, flow = self._build(db)
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        with pytest.raises(AppError, match="不是本节点的前序"):
            engine.act(
                assignment_id=_assignment_of(db, instance.id, first).id,
                actor=first, action="RETURN", return_target="s3",
            )

    def test_return_targets_respect_whitelist(self, db):
        initiator = _user(db)
        a = _user(db)
        second = _user(db)   # 注意：发起人不能当自己的审批人（引擎会剔除），所以另建一个
        form = _published_form(db, initiator)
        flow = _published_flow(db, initiator, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "一级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [a.id]}]}},
                {"id": "s2", "type": "approval", "name": "二级", "return_targets": [],
                 "assignee": {"sources": [{"type": "user", "user_ids": [second.id]}]}},
            ],
        })
        instance = _draft_instance(db, flow, form, initiator)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=initiator, data={"reason": "x"})
        engine.act(assignment_id=_assignment_of(db, instance.id, a).id, actor=a, action="AGREE")

        # return_targets=[] 明确禁止退回
        with pytest.raises(AppError, match="不能退回到"):
            engine.act(
                assignment_id=_assignment_of(db, instance.id, second).id,
                actor=second, action="RETURN", return_target="s1",
            )


# --------------------------------------------------------------------------- 撤回 / 终止


class TestWithdrawAndTerminate:
    def test_withdraw_before_any_action(self, db):
        admin = _user(db)
        approver = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{"id": "s1", "type": "approval", "name": "A",
                       "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]}}],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        engine.withdraw(instance=instance, actor=admin, reason="不需要了")

        assert instance.status == InstanceStatus.WITHDRAWN
        assert _pending_tasks(db, instance.id) == []

    def test_withdraw_blocked_after_someone_acted(self, db):
        admin = _user(db)
        approver = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "A",
                 "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]}},
                {"id": "s2", "type": "approval", "name": "B",
                 "assignee": {"sources": [{"type": "user", "user_ids": [admin.id]}]}},
            ],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        engine.act(assignment_id=_assignment_of(db, instance.id, approver).id, actor=approver, action="AGREE")

        with pytest.raises(AppError, match="已经有任务被处理过"):
            engine.withdraw(instance=instance, actor=admin)

    def test_cc_read_does_not_block_withdraw(self, db):
        """抄送已读不算「被处理过」（PRD §3.5.4 明确把抄送排除在撤回条件之外）。

        场景：流程**开头就是抄送**（抄送节点不占令牌，提交后立即派发并继续），
        此时还没有任何审批任务被处理过，撤回应当成功 ——
        即使有人已经读过抄送。
        """
        admin = _user(db)
        approver, watcher = _user(db), _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [
                {"id": "c0", "type": "cc", "name": "开局知会",
                 "cc_to": {"sources": [{"type": "user", "user_ids": [watcher.id]}]}},
                {"id": "s1", "type": "approval", "name": "A",
                 "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]}},
            ],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})

        # 抄送已随提交派发（不阻塞主线，s1 的待办也在）
        cc_assignment = db.scalar(
            select(TaskAssignment).where(
                TaskAssignment.instance_id == instance.id, TaskAssignment.user_id == watcher.id
            )
        )
        assert cc_assignment is not None
        engine.mark_cc_read(assignment_id=cc_assignment.id, actor=watcher)
        assert cc_assignment.is_read is True

        # 抄送已读不影响撤回
        engine.withdraw(instance=instance, actor=admin)
        assert instance.status == InstanceStatus.WITHDRAWN

    def test_terminate_requires_reason(self, db):
        admin = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {"steps": []})
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        with pytest.raises(AppError, match="必须填写原因"):
            engine.terminate(instance=instance, actor=admin, reason="  ")

    def test_terminate_cancels_everything(self, db):
        admin = _user(db)
        approver = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{"id": "s1", "type": "approval", "name": "A",
                       "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]}}],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        engine.terminate(instance=instance, actor=admin, reason="合规检查")

        assert instance.status == InstanceStatus.TERMINATED
        assert instance.terminated_reason == "合规检查"
        assert _pending_tasks(db, instance.id) == []


# --------------------------------------------------------------------------- 权限与可见性


class TestFieldPermissions:
    def test_supplement_field_hidden_until_opened(self, db):
        """PRD 验收点：财务补充字段在申请阶段完全不可见，财务节点才可编辑。"""
        initiator = _user(db)
        manager = _user(db)
        finance = _user(db)
        form = _published_form(db, initiator)
        flow = _published_flow(db, initiator, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "经理",
                 "assignee": {"sources": [{"type": "user", "user_ids": [manager.id]}]}},
                {"id": "s2", "type": "fill", "name": "财务补充",
                 "fields_permission": {
                     "base": "hidden",
                     "overrides": {"actualAmount": "editable-required"},
                 },
                 "assignee": {"sources": [{"type": "user", "user_ids": [finance.id]}]}},
            ],
        })
        instance = _draft_instance(db, flow, form, initiator)
        db.commit()

        engine = _engine(db)
        # 申请阶段就尝试写补充字段 —— 应当被忽略
        engine.submit(
            instance=instance, actor=initiator,
            data={"reason": "x", "actualAmount": 99999},
        )
        assert instance.current_data.get("actualAmount") is None

        # 经理节点：补充字段仍不可见，往 patch 里塞也被忽略
        engine.act(
            assignment_id=_assignment_of(db, instance.id, manager).id,
            actor=manager, action="AGREE", field_patch={"actualAmount": 12345},
        )
        assert instance.current_data.get("actualAmount") is None

        # 财务节点：可编辑，且是必填
        engine.act(
            assignment_id=_assignment_of(db, instance.id, finance).id,
            actor=finance, action="SUBMIT", field_patch={"actualAmount": 800},
        )
        assert instance.current_data["actualAmount"] == 800
        assert instance.status == InstanceStatus.APPROVED

    def test_supplement_field_is_required_at_target_node(self, db):
        """目标节点把补充字段配成 editable-required 时，不填就过不去。"""
        initiator = _user(db)
        finance = _user(db)
        form = _published_form(db, initiator)
        flow = _published_flow(db, initiator, form, {
            "steps": [
                {"id": "s2", "type": "fill", "name": "财务补充",
                 "fields_permission": {
                     "base": "hidden",
                     "overrides": {"actualAmount": "editable-required"},
                 },
                 "assignee": {"sources": [{"type": "user", "user_ids": [finance.id]}]}},
            ],
        })
        instance = _draft_instance(db, flow, form, initiator)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=initiator, data={"reason": "x"})
        with pytest.raises(AppError, match="必填"):
            engine.act(
                assignment_id=_assignment_of(db, instance.id, finance).id,
                actor=finance, action="SUBMIT",
            )

    def test_readonly_field_patch_ignored(self, db):
        """申请区在审批节点只读 —— 审批人改不动申请人的字段。"""
        admin = _user(db)
        approver = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{"id": "s1", "type": "approval", "name": "A",
                       "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]}}],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "原值", "amount": 100})
        engine.act(
            assignment_id=_assignment_of(db, instance.id, approver).id,
            actor=approver, action="AGREE", field_patch={"reason": "被改了", "amount": 999},
        )

        assert instance.current_data["reason"] == "原值"
        assert instance.current_data["amount"] == 100

    def test_field_meta_records_source(self, db):
        admin = _user(db)
        finance = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{"id": "s1", "type": "fill", "name": "补充",
                       "fields_permission": {"base": "hidden", "overrides": {"actualAmount": "editable"}},
                       "assignee": {"sources": [{"type": "user", "user_ids": [finance.id]}]}}],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        engine.act(
            assignment_id=_assignment_of(db, instance.id, finance).id,
            actor=finance, action="SUBMIT", field_patch={"actualAmount": 50},
        )

        meta = instance.field_meta or {}
        assert "actualAmount" in meta
        assert meta["actualAmount"]["node"] == "s1"
        assert meta["actualAmount"]["actor_id"] == finance.id


# --------------------------------------------------------------------------- 幂等与并发


class TestIdempotency:
    def test_double_act_rejected(self, db):
        admin = _user(db)
        approver = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{"id": "s1", "type": "approval", "name": "A",
                       "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]}}],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        assignment_id = _assignment_of(db, instance.id, approver).id
        engine.act(assignment_id=assignment_id, actor=approver, action="AGREE")

        # 重复点击 → 409 而不是产生第二条动作
        with pytest.raises(AppError, match="已处理或已取消"):
            engine.act(assignment_id=assignment_id, actor=approver, action="AGREE")

    def test_action_rows_carry_action_seq(self, db):
        admin = _user(db)
        approver = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{"id": "s1", "type": "approval", "name": "A",
                       "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]}}],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        engine.act(assignment_id=_assignment_of(db, instance.id, approver).id, actor=approver, action="AGREE")

        from app.models import InstanceAction

        rows = list(
            db.scalars(
                select(InstanceAction).where(InstanceAction.instance_id == instance.id)
                .order_by(InstanceAction.id)
            ).all()
        )
        # 提交（实例级，task_id=0）+ 审批动作
        assert [r.action for r in rows] == ["SUBMIT", "AGREE"]
        assert rows[0].task_id == 0            # 实例级动作用 0 而不是 NULL
        assert rows[1].action_seq == 1

    def test_other_users_assignment_rejected(self, db):
        admin = _user(db)
        approver = _user(db)
        stranger = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{"id": "s1", "type": "approval", "name": "A",
                       "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]}}],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        with pytest.raises(AppError, match="不是分配给你的任务"):
            engine.act(
                assignment_id=_assignment_of(db, instance.id, approver).id,
                actor=stranger, action="AGREE",
            )

    def test_notifications_are_deduplicated(self, db):
        admin = _user(db)
        approver = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{"id": "s1", "type": "approval", "name": "A",
                       "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]}}],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})

        keys = [
            r[0]
            for r in db.execute(
                select(Notification.dedup_key).where(Notification.user_id == approver.id)
            ).all()
        ]
        assert len(keys) == len(set(keys)), "通知去重键不应重复"


# --------------------------------------------------------------------------- 审批人解析


class TestApproverResolution:
    def test_dept_manager_resolution(self, db):
        hq = db.scalar(select(Department).where(Department.code == "HQ"))
        assert hq is not None
        manager = _user(db, dept_id=hq.id)
        employee = _user(db, dept_id=hq.id)
        hq.manager_user_id = manager.id
        db.flush()

        form = _published_form(db, manager)
        flow = _published_flow(db, manager, form, {
            "steps": [{"id": "s1", "type": "approval", "name": "主管审批",
                       "assignee": {"sources": [{"type": "dept_manager"}]}}],
        })
        instance = _draft_instance(db, flow, form, employee, reason="x")
        db.commit()

        _engine(db).submit(instance=instance, actor=employee, data={"reason": "x"})
        tasks = _pending_tasks(db, instance.id)
        assert len(tasks) == 1
        assignment = db.scalar(
            select(TaskAssignment).where(TaskAssignment.task_id == tasks[0].id)
        )
        assert assignment.user_id == manager.id

    def test_unresolved_approver_goes_to_admin_and_flagged(self, db):
        """PRD §3.3.2：未命中审批人 → 转管理员并标记异常，**不静默通过**。

        注意节点是默认的 SINGLE 模式，所以只会派给**第一个**管理员 ——
        这里断言「拿到任务的人是超管」，而不是某个具体 id
        （种子数据里本来就有一个超管）。
        """
        superuser = _user(db)
        superuser.is_superuser = True
        employee = _user(db)
        db.flush()

        form = _published_form(db, employee)
        flow = _published_flow(db, employee, form, {
            "steps": [{
                "id": "s1", "type": "approval", "name": "需要表单人员字段",
                # 引用的是文本字段，解析不出人员 → 必然未命中
                "assignee": {"sources": [{"type": "form_user_field", "field": "reason"}]},
            }],
        })
        instance = _draft_instance(db, flow, form, employee, reason="x")
        db.commit()

        _engine(db).submit(instance=instance, actor=employee, data={"reason": "x"})

        tasks = _pending_tasks(db, instance.id)
        assert len(tasks) == 1
        assert tasks[0].abnormal is True
        assert "管理员" in (tasks[0].abnormal_reason or "")
        assert instance.abnormal is True

        assignments = db.scalars(
            select(TaskAssignment).where(TaskAssignment.task_id == tasks[0].id)
        ).all()
        assert len(assignments) == 1
        assigned = db.get(User, assignments[0].user_id)
        assert assigned is not None and assigned.is_superuser is True
        assert assigned.id in {superuser.id, *(a.id for a in _superusers(db))}

    def test_initiator_is_not_own_approver(self, db):
        admin = _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [{"id": "s1", "type": "approval", "name": "自审",
                       "assignee": {"sources": [{"type": "user", "user_ids": [admin.id]}]}}],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        _engine(db).submit(instance=instance, actor=admin, data={"reason": "x"})
        tasks = _pending_tasks(db, instance.id)
        # 发起人被剔除后无人可派 → 转管理员（这里 admin 就是唯一用户，仍标记异常）
        assert tasks[0].abnormal is True


# --------------------------------------------------------------------------- 抄送


class TestCc:
    def test_cc_does_not_block_mainline(self, db):
        admin = _user(db)
        approver, watcher = _user(db), _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "A",
                 "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]}},
                {"id": "c1", "type": "cc", "name": "抄送HR",
                 "cc_to": {"sources": [{"type": "user", "user_ids": [watcher.id]}]}},
            ],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        engine.act(assignment_id=_assignment_of(db, instance.id, approver).id, actor=approver, action="AGREE")

        # 抄送不阻塞：实例直接通过，且没有活跃令牌
        assert instance.status == InstanceStatus.APPROVED
        assert _blocking_pending(db, instance.id) == []

        # 抄送人有知会记录（待办列表里以「抄送给我」呈现）
        cc = db.scalar(
            select(TaskAssignment).where(
                TaskAssignment.instance_id == instance.id, TaskAssignment.user_id == watcher.id
            )
        )
        assert cc is not None
        cc_task = db.get(Task, cc.task_id)
        assert cc_task is not None
        assert cc_task.node_type == "CC"
        assert cc_task.blocks_flow is False

    def test_cc_between_nodes_does_not_block(self, db):
        """抄送夹在两个审批之间时，主线要立即继续到下一个审批节点。"""
        admin = _user(db)
        a, watcher, b = _user(db), _user(db), _user(db)
        form = _published_form(db, admin)
        flow = _published_flow(db, admin, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "一级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [a.id]}]}},
                {"id": "c1", "type": "cc", "name": "抄送",
                 "cc_to": {"sources": [{"type": "user", "user_ids": [watcher.id]}]}},
                {"id": "s2", "type": "approval", "name": "二级",
                 "assignee": {"sources": [{"type": "user", "user_ids": [b.id]}]}},
            ],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "x"})
        engine.act(assignment_id=_assignment_of(db, instance.id, a).id, actor=a, action="AGREE")

        # 抄送派发的同时，二级审批的待办也已经生成
        assert instance.status == InstanceStatus.RUNNING
        assert [t.node_key for t in _blocking_pending(db, instance.id)] == ["s2"]
        cc = db.scalar(
            select(TaskAssignment).where(
                TaskAssignment.instance_id == instance.id, TaskAssignment.user_id == watcher.id
            )
        )
        assert cc is not None


# --------------------------------------------------------------------------- 机制 C：运行中追加字段


def _render_perms(db, instance, viewer: User) -> tuple[dict, dict]:
    """详情页的字段权限表 + 完整渲染数据（与前端拿到的是同一份）。"""
    from app.services.render_service import render_instance

    data = render_instance(db, instance, viewer=viewer)
    return data["permissions"], data


class TestExtFields:
    """PRD §3.4 机制 C / F5.1：报销跑到一半追加「合同编号」。

    约束（PRD 明列）：只作用于该实例、追加后不可物理删除、归档后不可追加、
    仅基础控件、默认只读仅目标节点可编辑、追加点之前不可见。
    """

    def _build(self, db):
        initiator = _user(db)
        manager = _user(db)
        finance = _user(db)
        form = _published_form(db, initiator)
        flow = _published_flow(db, initiator, form, {
            "steps": [
                {"id": "s1", "type": "approval", "name": "经理审批",
                 "assignee": {"sources": [{"type": "user", "user_ids": [manager.id]}]}},
                {"id": "s2", "type": "fill", "name": "财务补充",
                 "assignee": {"sources": [{"type": "user", "user_ids": [finance.id]}]}},
            ],
        })
        instance = _draft_instance(db, flow, form, initiator)
        db.commit()

        engine = _engine(db)
        engine.submit(instance=instance, actor=initiator, data={"reason": "出差"})
        return initiator, manager, finance, instance, engine

    def _append(self, engine, instance, actor, **kw):
        """追加一个字段并返回它的 ORM 行。"""
        spec = ExtFieldSpec(label=kw.pop("label", "合同编号"), type=kw.pop("type", "text"), **kw)
        engine.add_ext_field(instance=instance, actor=actor, spec=spec)
        return max(instance.ext_fields, key=lambda f: f.seq)

    # ---- 追加本身 ----

    def test_append_defaults_to_current_node(self, db):
        _, manager, _, instance, engine = self._build(db)

        row = self._append(engine, instance, manager)

        # key 带 ext_ 前缀与序号，不与模板字段冲突（PRD §3.4）
        assert row.field_key.startswith("ext_1_")
        assert instance.ext_field_seq == 1
        # 没指定目标节点 → 默认当前待办节点，且从这里开始可见
        assert row.editable_node_ids == ["s1"]
        assert row.visible_from_node_id == "s1"
        assert row.status == "ACTIVE"

    def test_append_writes_action_and_snapshot(self, db):
        _, manager, _, instance, engine = self._build(db)

        row = self._append(engine, instance, manager)

        action = db.scalar(
            select(InstanceAction).where(
                InstanceAction.instance_id == instance.id,
                InstanceAction.action == "ADD_EXT_FIELD",
            )
        )
        assert action is not None
        snap = db.get(DataSnapshot, action.snapshot_id)
        assert snap is not None and snap.kind == "EXT_FIELD"
        # 快照存了字段**定义** —— 停用后仍能还原当时的表单
        assert snap.data["ext_fields"][0]["field_key"] == row.field_key

    def test_ext_field_goes_to_instance_schema_only(self, db):
        """动态字段进实例的 data_schema，模板版本本身不动（只作用于该实例）。"""
        _, manager, _, instance, engine = self._build(db)
        template_schema = db.get(FormVersion, instance.form_version_id).schema

        row = self._append(engine, instance, manager)

        merged_keys = [
            f["key"] for s in instance.data_schema["sections"] for f in s["fields"]
        ]
        assert row.field_key in merged_keys
        assert db.get(FormVersion, instance.form_version_id).schema == template_schema

    # ---- 权限：谁看得见、谁能写 ----

    def test_editable_at_append_node_readonly_after(self, db):
        _, manager, finance, instance, engine = self._build(db)
        row = self._append(engine, instance, manager)

        perms, data = _render_perms(db, instance, manager)
        assert perms[row.field_key]["visible"] and perms[row.field_key]["editable"]
        # 前端拿到的是合并后的 schema，不必自己区分模板字段与动态字段
        assert any(
            f["key"] == row.field_key and f["label"] == "合同编号"
            for s in data["schema_data"]["sections"] for f in s["fields"]
        )

        # 处理人写入 → 落库
        engine.act(
            assignment_id=_assignment_of(db, instance.id, manager).id,
            actor=manager, action="AGREE", field_patch={row.field_key: "HT-2026-001"},
        )
        assert instance.current_data[row.field_key] == "HT-2026-001"

        # 后续节点（财务）看得见、但只读 —— 默认只读，仅目标节点可编辑
        perms, _ = _render_perms(db, instance, finance)
        assert perms[row.field_key]["visible"] and not perms[row.field_key]["editable"]

        # 财务往 patch 里塞也改不动
        engine.act(
            assignment_id=_assignment_of(db, instance.id, finance).id,
            actor=finance, action="SUBMIT", field_patch={row.field_key: "改一下"},
        )
        assert instance.current_data[row.field_key] == "HT-2026-001"

    def test_invisible_to_earlier_viewers(self, db):
        """追加点之前的节点不可见 —— 发起人此刻看不到。"""
        initiator, manager, _, instance, engine = self._build(db)
        row = self._append(engine, instance, manager)

        perms, data = _render_perms(db, instance, initiator)
        assert perms[row.field_key]["visible"] is False
        # 结构里仍带着定义，管理员才能管理它
        assert data["ext_fields"][0]["field_key"] == row.field_key

    def test_visible_to_initiator_after_archive(self, db):
        initiator, manager, finance, instance, engine = self._build(db)
        row = self._append(engine, instance, manager)
        engine.act(
            assignment_id=_assignment_of(db, instance.id, manager).id,
            actor=manager, action="AGREE", field_patch={row.field_key: "HT-2026-001"},
        )
        engine.act(
            assignment_id=_assignment_of(db, instance.id, finance).id, actor=finance, action="SUBMIT"
        )
        assert instance.status == InstanceStatus.APPROVED

        # 终态 → 归档视角：全可见、全只读（与补充字段同一条 PRD 验收点）
        perms, _ = _render_perms(db, instance, initiator)
        assert perms[row.field_key]["visible"] and not perms[row.field_key]["editable"]

    def test_required_enforced_only_where_editable(self, db):
        _, manager, finance, instance, engine = self._build(db)
        row = self._append(engine, instance, manager, required=True)

        # 可编辑节点上必填：不填过不去
        with pytest.raises(AppError, match="必填"):
            engine.act(
                assignment_id=_assignment_of(db, instance.id, manager).id,
                actor=manager, action="AGREE",
            )

        engine.act(
            assignment_id=_assignment_of(db, instance.id, manager).id,
            actor=manager, action="AGREE", field_patch={row.field_key: "HT-1"},
        )
        # 只读节点上不再是必填 —— 财务不填也能过
        engine.act(
            assignment_id=_assignment_of(db, instance.id, finance).id, actor=finance, action="SUBMIT"
        )
        assert instance.status == InstanceStatus.APPROVED

    def test_explicit_target_node(self, db):
        """指定「仅财务节点可编辑」—— 经理那边只读。"""
        _, manager, finance, instance, engine = self._build(db)
        row = self._append(engine, instance, manager, editable_node_ids=("s2",))

        perms, _ = _render_perms(db, instance, manager)
        assert perms[row.field_key]["visible"] and not perms[row.field_key]["editable"]

        engine.act(assignment_id=_assignment_of(db, instance.id, manager).id, actor=manager, action="AGREE")
        perms, _ = _render_perms(db, instance, finance)
        assert perms[row.field_key]["editable"]

        engine.act(
            assignment_id=_assignment_of(db, instance.id, finance).id,
            actor=finance, action="SUBMIT", field_patch={row.field_key: "HT-9"},
        )
        assert instance.current_data[row.field_key] == "HT-9"

    # ---- 停用 / 归档守卫 ----

    def test_disable_hides_field_but_keeps_data(self, db):
        _, manager, finance, instance, engine = self._build(db)
        row = self._append(engine, instance, manager)
        engine.act(
            assignment_id=_assignment_of(db, instance.id, manager).id,
            actor=manager, action="AGREE", field_patch={row.field_key: "HT-2026-001"},
        )

        engine.disable_ext_field(instance=instance, actor=manager, field_key=row.field_key)

        assert instance.ext_fields[0].status == "DISABLED"
        # 界面上消失：schema 与权限表里都没有它
        perms, data = _render_perms(db, instance, finance)
        assert row.field_key not in perms
        assert not any(
            f["key"] == row.field_key for s in data["schema_data"]["sections"] for f in s["fields"]
        )
        # 但**数据留着** —— 不可物理删除（PRD F5.3）
        assert instance.current_data[row.field_key] == "HT-2026-001"
        assert data["ext_fields"] == []   # 管理入口的列表里也不再出现

    def test_disable_twice_rejected(self, db):
        _, manager, _, instance, engine = self._build(db)
        row = self._append(engine, instance, manager)

        engine.disable_ext_field(instance=instance, actor=manager, field_key=row.field_key)
        with pytest.raises(AppError, match="停用"):
            engine.disable_ext_field(instance=instance, actor=manager, field_key=row.field_key)
        with pytest.raises(AppError, match="不存在"):
            engine.disable_ext_field(instance=instance, actor=manager, field_key="ext_999_x")

    def test_archive_blocks_further_changes(self, db):
        _, manager, finance, instance, engine = self._build(db)
        engine.act(assignment_id=_assignment_of(db, instance.id, manager).id, actor=manager, action="AGREE")
        engine.act(
            assignment_id=_assignment_of(db, instance.id, finance).id, actor=finance, action="SUBMIT"
        )
        assert instance.status == InstanceStatus.APPROVED

        with pytest.raises(AppError, match="归档"):
            self._append(engine, instance, manager)

    # ---- 控件白名单 ----

    def test_only_basic_field_types(self, db):
        """不支持子表与公式（PRD §3.4）。"""
        _, manager, _, instance, engine = self._build(db)
        for bad in ("subtable", "formula"):
            with pytest.raises(ExtFieldError, match="基础控件"):
                engine.add_ext_field(
                    instance=instance, actor=manager,
                    spec=ExtFieldSpec(label="X", type=bad),
                )

    def test_label_and_options_validated(self, db):
        _, manager, _, instance, engine = self._build(db)
        with pytest.raises(ExtFieldError, match="不能为空"):
            engine.add_ext_field(
                instance=instance, actor=manager, spec=ExtFieldSpec(label="  ", type="text")
            )
        with pytest.raises(ExtFieldError, match="选项"):
            engine.add_ext_field(
                instance=instance, actor=manager, spec=ExtFieldSpec(label="X", type="select")
            )

    # ---- 通知 ----

    def test_notifies_current_handlers(self, db):
        _, manager, _, instance, engine = self._build(db)
        row = self._append(engine, instance, manager)

        notif = db.scalar(
            select(Notification).where(
                Notification.user_id == manager.id, Notification.type == "EXT_FIELD_ADDED"
            )
        )
        assert notif is not None
        assert "合同编号" in notif.content
        # 同名字段追加两次 → 两条通知（dedup 里用的是 field_key 而不是 label）
        row2 = self._append(engine, instance, manager)
        assert row2.field_key != row.field_key
        count = db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == manager.id, Notification.type == "EXT_FIELD_ADDED")
        )
        assert count == 2


# --------------------------------------------------------------------------- 字段值规则（服务端强制）


class TestValueRules:
    """前端 `validateValues` 只是即时提示 —— 接口能被直接调用，规则必须落在服务端。

    纯规则语义见 `test_value_rules.py`，这里验证「提交/处理时真的会拦」。
    """

    RISKY_SCHEMA = {
        "sections": [{
            "key": "sec_apply", "title": "申请信息", "stage": "apply", "fields": [
                {"key": "reason", "label": "事由", "type": "text", "required": True,
                 "validators": {"min_length": 2, "max_length": 10}},
                {"key": "level", "label": "级别", "type": "select",
                 "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]},
                {"key": "amount", "label": "金额", "type": "number",
                 "validators": {"min": 1, "max": 1000}},
            ],
        }],
    }

    def _build(self, db):
        admin = _user(db)
        approver = _user(db)
        form = _published_form(db, admin)
        form.schema = self.RISKY_SCHEMA
        db.flush()
        flow = _published_flow(db, admin, form, {
            "steps": [{
                "id": "s1", "type": "approval", "name": "经理审批",
                "assignee": {"sources": [{"type": "user", "user_ids": [approver.id]}]},
            }],
        })
        instance = _draft_instance(db, flow, form, admin)
        db.commit()
        return admin, approver, instance

    def test_submit_rejects_out_of_range_number(self, db):
        admin, _approver, instance = self._build(db)

        with pytest.raises(AppError, match="不能大于 1000"):
            _engine(db).submit(
                instance=instance, actor=admin, data={"reason": "出差", "amount": 99999}
            )

    def test_submit_rejects_value_outside_options(self, db):
        admin, _approver, instance = self._build(db)

        with pytest.raises(AppError, match="选项"):
            _engine(db).submit(
                instance=instance, actor=admin, data={"reason": "出差", "level": "z"}
            )

    def test_submit_rejects_short_text(self, db):
        admin, _approver, instance = self._build(db)

        with pytest.raises(AppError, match="至少 2 个字符"):
            _engine(db).submit(instance=instance, actor=admin, data={"reason": "x"})

    def test_error_carries_per_field_issues(self, db):
        """错误体里带上每个字段的引用，前端才能高亮到具体控件。"""
        admin, _approver, instance = self._build(db)

        with pytest.raises(AppError) as excinfo:
            _engine(db).submit(instance=instance, actor=admin, data={"reason": "x", "amount": 0})

        extra = getattr(excinfo.value, "extra", {}) or {}
        keys = {issue["key"] for issue in extra.get("issues", [])}
        assert keys == {"reason", "amount"}

    def test_act_validates_the_patched_field(self, db):
        """处理人在节点上改字段时同样要过规则 —— 前端绕过去也拦得住。"""
        admin, approver, instance = self._build(db)
        engine = _engine(db)
        engine.submit(instance=instance, actor=admin, data={"reason": "出差"})

        # 申请区在审批节点默认只读，先给经理开「金额可编辑」——
        # 引擎每次调用都重新编译定义，改完重新赋值即可生效
        from app.models import FlowVersion

        version = db.get(FlowVersion, instance.flow_version_id)
        steps = [dict(step) for step in version.definition["steps"]]
        steps[0]["fields_permission"] = {"base": "hidden", "overrides": {"amount": "editable"}}
        version.definition = {**version.definition, "steps": steps}
        db.flush()

        with pytest.raises(AppError, match="不能小于 1"):
            engine.act(
                assignment_id=_assignment_of(db, instance.id, approver).id,
                actor=approver, action="AGREE", field_patch={"amount": 0},
            )
