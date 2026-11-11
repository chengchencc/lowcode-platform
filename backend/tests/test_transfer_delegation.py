"""转办与委托（M14）。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.clock import utcnow
from app.core.constants import AssignmentStatus, DelegationStatus
from app.core.errors import UnprocessableError
from app.models import Delegation, InstanceAction, Notification, TaskAssignment
from app.services import instance_service
from tests.test_engine_service import (
    _draft_instance,
    _engine,
    _published_flow,
    _published_form,
    _user,
)

BASE = "/api/v1"


def _flow_with_approver(db, approver):
    owner = _user(db)
    form = _published_form(db, owner)
    flow = _published_flow(
        db,
        owner,
        form,
        {
            "steps": [{
                "id": "s1",
                "type": "approval",
                "name": "经理审批",
                "assignee": {"mode": "SINGLE", "sources": [{"type": "user", "user_ids": [approver.id]}]},
            }]
        },
    )
    return form, flow


def _submit(db, form, flow, initiator):
    instance = _draft_instance(db, flow, form, initiator)
    db.commit()
    _engine(db).submit(instance=instance, actor=initiator, data={"reason": "出差"})
    return instance


def _pending_of(db, instance_id: int, user_id: int) -> TaskAssignment:
    assignment = db.scalar(
        select(TaskAssignment).where(
            TaskAssignment.instance_id == instance_id,
            TaskAssignment.user_id == user_id,
            TaskAssignment.status == AssignmentStatus.PENDING,
        )
    )
    assert assignment is not None
    return assignment


def test_transfer_reassigns_and_leaves_trace(db):
    initiator = _user(db)
    approver = _user(db)
    target = _user(db)
    form, flow = _flow_with_approver(db, approver)
    instance = _submit(db, form, flow, initiator)
    assignment = _pending_of(db, instance.id, approver.id)

    _engine(db).transfer(
        assignment_id=assignment.id,
        actor=approver,
        to_user_id=target.id,
        reason="出差，请同事代办",
    )

    db.refresh(assignment)
    assert assignment.status == AssignmentStatus.CANCELLED
    assert assignment.cancel_reason == "TRANSFERRED"

    new_assignment = db.scalar(
        select(TaskAssignment).where(
            TaskAssignment.instance_id == instance.id,
            TaskAssignment.user_id == target.id,
            TaskAssignment.status == AssignmentStatus.PENDING,
        )
    )
    assert new_assignment is not None
    assert new_assignment.origin_user_id == approver.id
    assert new_assignment.origin_kind == "TRANSFER"

    action = db.scalar(
        select(InstanceAction).where(
            InstanceAction.instance_id == instance.id,
            InstanceAction.action == "TRANSFER",
        )
    )
    assert action is not None and action.actor_id == approver.id

    notification = db.scalar(
        select(Notification).where(
            Notification.user_id == target.id,
            Notification.type == "TASK_TRANSFERRED",
        )
    )
    assert notification is not None

    # 原处理人仍能看到该实例（历史参与人）
    stmt = instance_service.build_query(db, user=approver, scope="all")
    assert instance in list(db.scalars(stmt).all())


def test_transfer_rejects_handled_assignment(db):
    initiator = _user(db)
    approver = _user(db)
    target = _user(db)
    form, flow = _flow_with_approver(db, approver)
    instance = _submit(db, form, flow, initiator)
    assignment = _pending_of(db, instance.id, approver.id)
    _engine(db).act(
        assignment_id=assignment.id,
        actor=approver,
        action="AGREE",
    )
    db.refresh(assignment)

    with pytest.raises(UnprocessableError):
        _engine(db).transfer(
            assignment_id=assignment.id,
            actor=approver,
            to_user_id=target.id,
            reason="晚了",
        )


def test_delegation_routes_new_task(db):
    initiator = _user(db)
    delegator = _user(db)
    delegatee = _user(db)
    form, flow = _flow_with_approver(db, delegator)
    now = utcnow()
    db.add(
        Delegation(
            delegator_id=delegator.id,
            delegatee_id=delegatee.id,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            reason="休假",
            status=DelegationStatus.ACTIVE,
        )
    )
    db.commit()

    instance = _submit(db, form, flow, initiator)

    assignment = _pending_of(db, instance.id, delegatee.id)
    assert assignment.origin_user_id == delegator.id
    assert assignment.origin_kind == "DELEGATION"

    # 委托人仍能查看详情
    stmt = instance_service.build_query(db, user=delegator, scope="all")
    assert instance in list(db.scalars(stmt).all())

    notifications = list(
        db.scalars(
            select(Notification).where(Notification.type == "TASK_DELEGATED")
        ).all()
    )
    assert {item.user_id for item in notifications} == {delegator.id, delegatee.id}


def test_delegation_api_validation(client, db, normal_headers, normal_user):
    other = _user(db)

    self_delegation = client.post(
        f"{BASE}/delegations",
        headers=normal_headers,
        json={
            "delegatee_id": normal_user.id,
            "start_at": (utcnow() + timedelta(hours=1)).isoformat(),
            "end_at": (utcnow() + timedelta(hours=2)).isoformat(),
            "reason": "自己委托给自己",
        },
    )
    assert self_delegation.status_code == 422
    assert self_delegation.json()["detail"]["code"] == "DELEGATION_SELF"

    payload = {
        "delegatee_id": other.id,
        "start_at": (utcnow() + timedelta(hours=1)).isoformat(),
        "end_at": (utcnow() + timedelta(hours=2)).isoformat(),
        "reason": "休假",
    }
    created = client.post(f"{BASE}/delegations", headers=normal_headers, json=payload)
    assert created.status_code == 201, created.text

    overlap_payload = {
        **payload,
        "start_at": (utcnow() + timedelta(hours=1, minutes=30)).isoformat(),
        "end_at": (utcnow() + timedelta(hours=3)).isoformat(),
    }
    overlap = client.post(
        f"{BASE}/delegations", headers=normal_headers, json=overlap_payload
    )
    assert overlap.status_code == 409
    assert overlap.json()["detail"]["code"] == "DELEGATION_OVERLAP"

    listed = client.get(f"{BASE}/delegations", headers=normal_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [created.json()["id"]]

    cancelled = client.post(
        f"{BASE}/delegations/{created.json()['id']}/cancel", headers=normal_headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
