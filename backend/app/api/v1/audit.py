"""操作审计查询（F6.6）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import AdminUser, DbSession
from app.core.pagination import Page, PageParams, build_page, paginate
from app.schemas.audit import AuditLogOut
from app.services import audit_service

router = APIRouter(prefix="/admin", tags=["审计"])


@router.get("/audit-logs", response_model=Page[AuditLogOut], summary="操作审计列表")
def list_audit_logs(
    db: DbSession,
    _: AdminUser,
    paging: Annotated[PageParams, Depends()],
    biz_type: Annotated[str | None, Query(description="USER/DEPT/ROLE/...")] = None,
    biz_id: Annotated[int | None, Query()] = None,
    actor_id: Annotated[int | None, Query()] = None,
) -> dict:
    stmt = audit_service.build_query(biz_type=biz_type, biz_id=biz_id, actor_id=actor_id)
    rows, total = paginate(db, stmt, paging)
    return build_page(rows, total, paging)
