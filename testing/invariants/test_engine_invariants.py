"""G3：引擎不变量随机序列测试。

目标不是覆盖具体业务分支，而是随机生成**合法**流程定义与动作序列，
持续检查那些不依赖实现路径的约束：

1. 状态只落在文档定义的集合里；
2. 任务/待办守恒：无孤儿、无「任务已完成但仍有待办」；
3. 非运行态不再有阻塞待办；
4. 同一任务同一人不会重复待办；
5. 快照 seq 严格递增；动作有 actor/time；版本在运行中不变；
6. 非法操作之外不产生未捕获异常。

失败时抛出的断言带 seed，便于复现。
"""

from __future__ import annotations

import os
import random

import pytest
from sqlalchemy import select

from app.core.constants import (
    AssignmentStatus,
    InstanceStatus,
    TaskStatus,
    TERMINAL_STATUSES,
)
from app.models import DataSnapshot, FlowInstance, InstanceAction, Task, TaskAssignment, User
from tests.test_engine_service import (
    _draft_instance,
    _engine,
    _pending_assignments,
    _published_flow,
    _published_form,
    _user,
)

pytestmark = pytest.mark.invariants

ALLOWED_INSTANCE = {
    InstanceStatus.RUNNING,
    InstanceStatus.REJECTED,
    InstanceStatus.APPROVED,
    InstanceStatus.WITHDRAWN,
    InstanceStatus.TERMINATED,
}
ALLOWED_TASK = {TaskStatus.PENDING, TaskStatus.COMPLETED, TaskStatus.CANCELLED}
ALLOWED_ASSIGNMENT = {
    AssignmentStatus.WAITING,
    AssignmentStatus.PENDING,
    AssignmentStatus.DONE,
    AssignmentStatus.CANCELLED,
}


def _approval(node_id: str, name: str, user_id: int) -> dict:
    return {
        "id": node_id,
        "type": "approval",
        "name": name,
        "assignee": {
            "mode": "SINGLE",
            "sources": [{"type": "user", "user_ids": [user_id]}],
        },
    }


def _definition(rng: random.Random, users: list[User]) -> dict:
    steps: list[dict] = []
    count = rng.randint(1, 3)
    for index in range(1, count + 1):
        roll = rng.random()
        if index > 1 and roll < 0.2:
            steps.append(
                {
                    "id": f"p{index}",
                    "type": "parallel",
                    "name": f"并行{index}",
                    "mode": rng.choice(["all", "any"]),
                    "members": [
                        _approval(f"m{index}a", f"成员{index}A", rng.choice(users).id),
                        _approval(f"m{index}b", f"成员{index}B", rng.choice(users).id),
                    ],
                }
            )
        elif index > 1 and roll < 0.38:
            steps.append(
                {
                    "id": f"c{index}",
                    "type": "condition",
                    "name": f"条件{index}",
                    "branches": [
                        {
                            "id": f"b{index}",
                            "when": {
                                "op": "and",
                                "conditions": [
                                    {"field": "amount", "cmp": ">", "value": 1000}
                                ],
                            },
                            "steps": [
                                _approval(
                                    f"a{index}b", f"分支审批{index}", rng.choice(users).id
                                )
                            ],
                        },
                        {"id": f"else{index}", "when": None, "steps": []},
                    ],
                }
            )
        else:
            steps.append(
                _approval(f"a{index}", f"审批{index}", rng.choice(users).id)
            )
    return {"steps": steps}


def _assert_invariants(db, instance: FlowInstance, version_ids: tuple[int, int]) -> None:
    db.flush()
    assert instance.status in ALLOWED_INSTANCE, instance.status
    assert (instance.flow_version_id, instance.form_version_id) == version_ids

    tasks = list(
        db.scalars(select(Task).where(Task.instance_id == instance.id)).all()
    )
    assignments = list(
        db.scalars(
            select(TaskAssignment).where(TaskAssignment.instance_id == instance.id)
        ).all()
    )
    actions = list(
        db.scalars(
            select(InstanceAction)
            .where(InstanceAction.instance_id == instance.id)
            .order_by(InstanceAction.id)
        ).all()
    )
    snapshots = list(
        db.scalars(
            select(DataSnapshot)
            .where(DataSnapshot.instance_id == instance.id)
            .order_by(DataSnapshot.seq)
        ).all()
    )

    assert all(task.status in ALLOWED_TASK for task in tasks)
    assert all(item.status in ALLOWED_ASSIGNMENT for item in assignments)

    task_by_id = {task.id: task for task in tasks}
    for assignment in assignments:
        task = task_by_id.get(assignment.task_id)
        assert task is not None, "孤儿待办：task 不存在"
        assert task.instance_id == instance.id
        if assignment.status == AssignmentStatus.PENDING:
            assert task.status == TaskStatus.PENDING, "待办挂在非活跃任务上"

    for task in tasks:
        if task.status == TaskStatus.COMPLETED:
            assert not any(
                item.task_id == task.id and item.status == AssignmentStatus.PENDING
                for item in assignments
            ), "已完成任务仍有待办"

    pending_pairs = [
        (item.task_id, item.user_id)
        for item in assignments
        if item.status == AssignmentStatus.PENDING
    ]
    assert len(pending_pairs) == len(set(pending_pairs)), "同一任务重复派给同一人"

    if instance.status != InstanceStatus.RUNNING:
        assert not any(
            task.status == TaskStatus.PENDING and task.blocks_flow for task in tasks
        ), f"{instance.status} 仍有阻塞待办"
        assert not pending_pairs, f"{instance.status} 仍有待办"

    seqs = [item.seq for item in snapshots]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs)), "快照 seq 不单调"
    assert all(item.round <= instance.round for item in snapshots)
    assert all(item.actor_id for item in actions), "动作缺少 actor"
    assert all(item.round <= instance.round for item in actions)


def _run_actions(
    db, rng: random.Random, instance: FlowInstance, initiator: User, data: dict
) -> None:
    engine = _engine(db)
    version_ids = (instance.flow_version_id, instance.form_version_id)

    for _ in range(30):
        _assert_invariants(db, instance, version_ids)
        if instance.status in TERMINAL_STATUSES:
            break
        if instance.status == InstanceStatus.REJECTED:
            if rng.random() < 0.6:
                engine.resubmit(instance=instance, actor=initiator, data=data)
                continue
            break

        pending = _pending_assignments(db, instance.id)
        if not pending:
            break
        assignment = rng.choice(pending)
        actor = db.get(User, assignment.user_id)
        assert actor is not None
        action = "REJECT" if rng.random() < 0.18 else "AGREE"
        engine.act(
            assignment_id=assignment.id,
            actor=actor,
            action=action,
            opinion="随机驳回" if action == "REJECT" else None,
        )

    _assert_invariants(db, instance, version_ids)


@pytest.mark.invariants
def test_random_flows_and_actions_preserve_invariants(db):
    rounds = int(os.environ.get("INVARIANT_ROUNDS", "200"))
    rng = random.Random(20261120)

    initiator = _user(db, "inv_initiator")
    approvers = [_user(db, f"inv_approver_{index}") for index in range(1, 4)]
    covered = {
        "parallel": False,
        "condition": False,
        "reject": False,
        "resubmit": False,
        "any": False,
        "all": False,
    }

    for seed in range(rounds):
        rng.seed(20261120 + seed)
        form = _published_form(db, initiator)
        definition = _definition(rng, approvers)
        flow = _published_flow(db, initiator, form, definition)
        data = {
            "reason": f"invariant-{seed}",
            "amount": rng.randint(0, 2000),
            "days": rng.randint(0, 5),
        }
        instance = _draft_instance(db, flow, form, initiator, **data)
        db.commit()

        for step in definition["steps"]:
            if step["type"] == "parallel":
                covered["parallel"] = True
                covered[step["mode"]] = True
            if step["type"] == "condition":
                covered["condition"] = True

        try:
            _engine(db).submit(instance=instance, actor=initiator, data=data)
            _run_actions(db, rng, instance, initiator, data)
        except Exception as exc:  # noqa: BLE001 - 失败必须带 seed 复现
            raise AssertionError(f"不变量失败，seed={seed}") from exc

        actions = list(
            db.scalars(
                select(InstanceAction.action).where(
                    InstanceAction.instance_id == instance.id
                )
            ).all()
        )
        if "REJECT" in actions:
            covered["reject"] = True
        if instance.round > 1:
            covered["resubmit"] = True

    missing = [key for key, hit in covered.items() if not hit]
    assert not missing, f"随机序列覆盖不足：{missing}"

