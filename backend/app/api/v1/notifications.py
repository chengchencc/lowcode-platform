"""站内消息接口（F7.1 / F7.2）。

前端以 ≤10s 的间隔轮询 `unread-count` 做角标，V1 不做 WebSocket。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.clock import utcnow
from app.core.deps import CurrentUser, DbSession
from app.core.pagination import Page, PageParams, build_page, paginate
from app.models import Notification
from app.schemas.common import OkResp
from app.schemas.instance import NotificationIdsRequest, NotificationOut

router = APIRouter(prefix="/notifications", tags=["消息"])


@router.get("", response_model=Page[NotificationOut], summary="消息列表")
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    paging: Annotated[PageParams, Depends()],
    unread_only: Annotated[bool, Query()] = False,
    notif_type: Annotated[str | None, Query(alias="type", description="按类型筛选")] = None,
) -> dict:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    if notif_type:
        stmt = stmt.where(Notification.type == notif_type)

    rows, total = paginate(db, stmt, paging)
    return build_page([NotificationOut.model_validate(r) for r in rows], total, paging)


@router.get("/unread-count", summary="未读消息数（角标轮询用）")
def unread_count(db: DbSession, user: CurrentUser) -> dict:
    count = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id, Notification.is_read.is_(False)
        )
    ) or 0
    return {"count": count}


@router.post("/{notification_id}/read", response_model=OkResp, summary="标记单条已读")
def mark_read(notification_id: int, db: DbSession, user: CurrentUser) -> OkResp:
    row = db.get(Notification, notification_id)
    if row is not None and row.user_id == user.id and not row.is_read:
        row.is_read = True
        row.read_at = utcnow()
        db.commit()
    return OkResp(message="已读")


@router.post("/read", response_model=OkResp, summary="批量已读")
def mark_many_read(
    payload: NotificationIdsRequest, db: DbSession, user: CurrentUser
) -> OkResp:
    if not payload.ids:
        return OkResp(message="没有需要标记的消息")

    rows = list(
        db.scalars(
            select(Notification).where(
                Notification.id.in_(set(payload.ids)),
                Notification.user_id == user.id,
                Notification.is_read.is_(False),
            )
        ).all()
    )
    now: datetime = utcnow()
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.commit()
    return OkResp(message=f"已标记 {len(rows)} 条为已读")


@router.post("/read-all", response_model=OkResp, summary="全部已读")
def mark_all_read(db: DbSession, user: CurrentUser) -> OkResp:
    rows = list(
        db.scalars(
            select(Notification).where(
                Notification.user_id == user.id, Notification.is_read.is_(False)
            )
        ).all()
    )
    now: datetime = utcnow()
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.commit()
    return OkResp(message=f"已标记 {len(rows)} 条为已读")
