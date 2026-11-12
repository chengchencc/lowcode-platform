"""委托代理（M14）。

委托只在**派发新任务**时生效：如果处理人在生效区间内有委托，
待办直接派给被委托人，并记录来源。已存在的待办不自动转交。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.constants import DelegationStatus, UserStatus
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.core.policy import is_admin
from app.models import Delegation, User


def _naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise UnprocessableError("被委托人不存在或已停用", code="DELEGATEE_INVALID")
    return user


def _validate_flow_ids(db: Session, flow_ids: list[int] | None) -> list[int] | None:
    if not flow_ids:
        return None
    from app.models import FlowTemplate

    existing = {
        row[0]
        for row in db.execute(
            select(FlowTemplate.id).where(FlowTemplate.id.in_(flow_ids))
        ).all()
    }
    missing = [flow_id for flow_id in flow_ids if flow_id not in existing]
    if missing:
        raise UnprocessableError(
            f"流程不存在：{', '.join(map(str, missing))}", code="DELEGATION_FLOW_INVALID"
        )
    return flow_ids


def _assert_not_overlapping(
    db: Session,
    *,
    delegator_id: int,
    start_at: datetime,
    end_at: datetime,
    exclude_id: int | None = None,
) -> None:
    stmt = select(Delegation).where(
        Delegation.delegator_id == delegator_id,
        Delegation.status == DelegationStatus.ACTIVE,
        and_(Delegation.start_at < end_at, Delegation.end_at > start_at),
    )
    if exclude_id is not None:
        stmt = stmt.where(Delegation.id != exclude_id)
    if db.scalar(stmt.limit(1)):
        raise ConflictError("该时段已有生效委托，不能重叠", code="DELEGATION_OVERLAP")


def active_delegation(
    db: Session, *, user_id: int, flow_template_id: int, at: datetime | None = None
) -> Delegation | None:
    moment = at or utcnow()
    rows = list(
        db.scalars(
            select(Delegation).where(
                Delegation.delegator_id == user_id,
                Delegation.status == DelegationStatus.ACTIVE,
                Delegation.start_at <= moment,
                Delegation.end_at > moment,
            )
        ).all()
    )
    for row in rows:
        if not row.flow_template_ids or flow_template_id in row.flow_template_ids:
            return row
    return None


def to_out(db: Session, delegation: Delegation) -> dict[str, Any]:
    delegator = db.get(User, delegation.delegator_id)
    delegatee = db.get(User, delegation.delegatee_id)
    return {
        "id": delegation.id,
        "delegator_id": delegation.delegator_id,
        "delegator_name": delegator.real_name if delegator else None,
        "delegatee_id": delegation.delegatee_id,
        "delegatee_name": delegatee.real_name if delegatee else None,
        "start_at": delegation.start_at,
        "end_at": delegation.end_at,
        "flow_template_ids": delegation.flow_template_ids,
        "reason": delegation.reason,
        "status": delegation.status,
        "created_at": delegation.created_at,
    }


def list_delegations(db: Session, user: User, *, all_users: bool = False) -> list[dict]:
    stmt = select(Delegation).order_by(Delegation.id.desc())
    if all_users:
        if not is_admin(user):
            raise ForbiddenError("只有管理员可以查看全部委托", code="ADMIN_REQUIRED")
    else:
        stmt = stmt.where(
            or_(Delegation.delegator_id == user.id, Delegation.delegatee_id == user.id)
        )
    return [to_out(db, row) for row in db.scalars(stmt).all()]


def get_or_404(db: Session, delegation_id: int) -> Delegation:
    delegation = db.get(Delegation, delegation_id)
    if delegation is None:
        raise NotFoundError("委托不存在", code="DELEGATION_NOT_FOUND")
    return delegation


def create_delegation(
    db: Session, payload, *, actor: User
) -> Delegation:
    if payload.delegatee_id == actor.id:
        raise UnprocessableError("不能委托给自己", code="DELEGATION_SELF")
    _get_user(db, payload.delegatee_id)
    start_at, end_at = _naive(payload.start_at), _naive(payload.end_at)
    if start_at >= end_at:
        raise UnprocessableError("结束时间必须晚于开始时间", code="DELEGATION_RANGE")
    _assert_not_overlapping(
        db, delegator_id=actor.id, start_at=start_at, end_at=end_at
    )
    delegation = Delegation(
        delegator_id=actor.id,
        delegatee_id=payload.delegatee_id,
        start_at=start_at,
        end_at=end_at,
        flow_template_ids=_validate_flow_ids(db, payload.flow_template_ids),
        reason=payload.reason,
        status=DelegationStatus.ACTIVE,
    )
    db.add(delegation)
    db.commit()
    db.refresh(delegation)
    return delegation


def update_delegation(
    db: Session, delegation: Delegation, payload, *, actor: User
) -> Delegation:
    if delegation.delegator_id != actor.id and not is_admin(actor):
        raise ForbiddenError("不能修改他人的委托", code="DELEGATION_FORBIDDEN")
    delegatee_id = payload.delegatee_id or delegation.delegatee_id
    if delegatee_id == delegation.delegator_id:
        raise UnprocessableError("不能委托给自己", code="DELEGATION_SELF")
    _get_user(db, delegatee_id)
    start_at = _naive(payload.start_at) if payload.start_at else delegation.start_at
    end_at = _naive(payload.end_at) if payload.end_at else delegation.end_at
    if start_at >= end_at:
        raise UnprocessableError("结束时间必须晚于开始时间", code="DELEGATION_RANGE")
    _assert_not_overlapping(
        db,
        delegator_id=delegation.delegator_id,
        start_at=start_at,
        end_at=end_at,
        exclude_id=delegation.id,
    )
    if "flow_template_ids" in payload.model_fields_set:
        delegation.flow_template_ids = _validate_flow_ids(db, payload.flow_template_ids)
    if payload.reason is not None:
        delegation.reason = payload.reason
    delegation.delegatee_id = delegatee_id
    delegation.start_at = start_at
    delegation.end_at = end_at
    db.commit()
    db.refresh(delegation)
    return delegation


def cancel_delegation(db: Session, delegation: Delegation, *, actor: User) -> Delegation:
    if delegation.delegator_id != actor.id and not is_admin(actor):
        raise ForbiddenError("不能取消他人的委托", code="DELEGATION_FORBIDDEN")
    delegation.status = DelegationStatus.CANCELLED
    db.commit()
    db.refresh(delegation)
    return delegation
