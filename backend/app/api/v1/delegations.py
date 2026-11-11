"""委托代理接口（M14）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import ClientIp, CurrentUser, DbSession
from app.schemas.delegation import (
    DelegationCreate,
    DelegationOut,
    DelegationUpdate,
)
from app.services import delegation_service

router = APIRouter(prefix="/delegations", tags=["委托"])


@router.get("", response_model=list[DelegationOut], summary="委托列表")
def list_delegations(
    db: DbSession,
    user: CurrentUser,
    all_users: Annotated[bool, Query()] = False,
) -> list[dict]:
    return delegation_service.list_delegations(db, user, all_users=all_users)


@router.post(
    "", response_model=DelegationOut, status_code=status.HTTP_201_CREATED,
    summary="新建委托",
)
def create_delegation(
    payload: DelegationCreate, db: DbSession, user: CurrentUser, ip: ClientIp
) -> dict:
    delegation = delegation_service.create_delegation(db, payload, actor=user)
    return delegation_service.to_out(db, delegation)


@router.put("/{delegation_id}", response_model=DelegationOut, summary="修改委托")
def update_delegation(
    delegation_id: int,
    payload: DelegationUpdate,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    delegation = delegation_service.get_or_404(db, delegation_id)
    delegation = delegation_service.update_delegation(
        db, delegation, payload, actor=user
    )
    return delegation_service.to_out(db, delegation)


@router.post("/{delegation_id}/cancel", response_model=DelegationOut, summary="取消委托")
def cancel_delegation(
    delegation_id: int, db: DbSession, user: CurrentUser
) -> dict:
    delegation = delegation_service.get_or_404(db, delegation_id)
    delegation = delegation_service.cancel_delegation(db, delegation, actor=user)
    return delegation_service.to_out(db, delegation)
