"""审计写入（F6.6）。所有写操作都应调用 `record`。"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
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
    action: str | None = None,
    keyword: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> Select:
    """审计检索（F6.6）。

    `keyword` 同时匹配摘要与操作人姓名：查审计的人往往只记得「谁改的」
    或者「改的是什么」，逼他先选类型反而不好用。
    """
    stmt = select(AuditLog)
    if biz_type:
        stmt = stmt.where(AuditLog.biz_type == biz_type)
    if biz_id is not None:
        stmt = stmt.where(AuditLog.biz_id == biz_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(AuditLog.summary.like(like) | AuditLog.actor_name.like(like))
    if created_from is not None:
        stmt = stmt.where(AuditLog.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(AuditLog.created_at <= created_to)
    return stmt.order_by(AuditLog.id.desc())


def list_logs(db: Session, stmt: Select, params: PageParams) -> tuple[list[AuditLog], int]:
    return paginate(db, stmt, params)


# --------------------------------------------------------------------------- 导出


def build_csv(rows: list[AuditLog]) -> str:
    """审计导出（CSV，带 BOM）。

    审计是合规材料，导出的列名用中文、时间按本地习惯写即可 ——
    它与 `audit_logs` 表的结构不必一一对应，可读比可机读更重要。
    """
    from app.core.constants import AUDIT_ACTION_LABELS, AUDIT_BIZ_LABELS

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["时间", "操作人", "对象类型", "对象ID", "动作", "摘要", "IP", "详情"])
    for row in rows:
        writer.writerow([
            row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "",
            row.actor_name or (f"#{row.actor_id}" if row.actor_id else "系统"),
            AUDIT_BIZ_LABELS.get(row.biz_type, row.biz_type),
            row.biz_id,
            AUDIT_ACTION_LABELS.get(row.action, row.action),
            row.summary or "",
            row.ip or "",
            json.dumps(row.detail, ensure_ascii=False) if row.detail else "",
        ])
    return "﻿" + buffer.getvalue()
