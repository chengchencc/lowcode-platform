"""审计写入（F6.6）。所有写操作都应调用 `record`。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.constants import AuditAction, AuditBizType
from app.core.pagination import PageParams, paginate
from app.models import AuditLog, User


def record(
    db: Session,
    *,
    actor: User | None,
    biz_type: AuditBizType | str,
    biz_id: int,
    action: AuditAction | str,
    summary: str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditLog:
    """追加一条审计记录。

    只 `add` 不 `commit` —— 让调用方与业务写操作在同一事务里提交，
    避免出现「业务回滚了但审计留下了」的脏记录。
    """
    log = AuditLog(
        actor_id=actor.id if actor else None,
        actor_name=actor.real_name if actor else None,
        biz_type=str(biz_type),
        biz_id=biz_id,
        action=str(action),
        summary=summary,
        detail=detail,
        ip=ip,
    )
    db.add(log)
    return log


def build_query(
    *,
    biz_type: str | None = None,
    biz_id: int | None = None,
    actor_id: int | None = None,
) -> Select:
    stmt = select(AuditLog)
    if biz_type:
        stmt = stmt.where(AuditLog.biz_type == biz_type)
    if biz_id is not None:
        stmt = stmt.where(AuditLog.biz_id == biz_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    return stmt.order_by(AuditLog.id.desc())


def list_logs(db: Session, stmt: Select, params: PageParams) -> tuple[list[AuditLog], int]:
    return paginate(db, stmt, params)
