"""操作审计查询（F6.6）。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from app.core.clock import utcnow
from app.core.deps import AdminUser, DbSession
from app.core.pagination import Page, PageParams, build_page, paginate
from app.schemas.audit import AuditLogOut
from app.services import audit_service

router = APIRouter(prefix="/admin", tags=["审计"])

#: 导出行数上限：审计表会长得很快，一次导全表既慢又没意义
MAX_EXPORT_ROWS = 5000


@router.get("/audit-logs", response_model=Page[AuditLogOut], summary="操作审计列表")
def list_audit_logs(
    db: DbSession,
    _: AdminUser,
    paging: Annotated[PageParams, Depends()],
    biz_type: Annotated[str | None, Query(description="USER/DEPT/ROLE/...")] = None,
    biz_id: Annotated[int | None, Query()] = None,
    actor_id: Annotated[int | None, Query()] = None,
    action: Annotated[str | None, Query(description="CREATE/UPDATE/PUBLISH/...")] = None,
    keyword: Annotated[str | None, Query(description="摘要或操作人姓名")] = None,
    created_from: Annotated[datetime | None, Query(description="起始时间（含）")] = None,
    created_to: Annotated[datetime | None, Query(description="截止时间（含）")] = None,
) -> dict:
    stmt = audit_service.build_query(
        biz_type=biz_type,
        biz_id=biz_id,
        actor_id=actor_id,
        action=action,
        keyword=keyword,
        created_from=created_from,
        created_to=created_to,
    )
    rows, total = paginate(db, stmt, paging)
    return build_page(rows, total, paging)


@router.get("/audit-logs/export", summary="导出审计 CSV")
def export_audit_logs(
    db: DbSession,
    _: AdminUser,
    biz_type: Annotated[str | None, Query()] = None,
    actor_id: Annotated[int | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    keyword: Annotated[str | None, Query()] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> Response:
    """按同一组条件导出（合规材料要能带走）。"""
    rows = list(
        db.scalars(
            audit_service.build_query(
                biz_type=biz_type,
                actor_id=actor_id,
                action=action,
                keyword=keyword,
                created_from=created_from,
                created_to=created_to,
            ).limit(MAX_EXPORT_ROWS)
        ).all()
    )
    filename = f"audit-{utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content=audit_service.build_csv(rows).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"audit.csv\"; filename*=UTF-8''{quote(filename)}"
            )
        },
    )

