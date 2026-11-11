"""工作量统计：协作表格（M12）。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.core.deps import AdminUser, ClientIp, CurrentUser, DbSession
from app.schemas.common import OkResp
from app.schemas.work_stat import (
    WorkStatImportPreview,
    WorkStatImportResult,
    WorkStatRowCreate,
    WorkStatRowLogOut,
    WorkStatRowOut,
    WorkStatRowUpdate,
    WorkStatSheetCreate,
    WorkStatSheetOut,
    WorkStatSheetUpdate,
)
from app.services import work_stat_service

router = APIRouter(prefix="/work-stat-sheets", tags=["工作量统计"])


@router.get("", response_model=list[WorkStatSheetOut], summary="我可见的统计表")
def list_sheets(db: DbSession, user: CurrentUser) -> list[dict]:
    return work_stat_service.list_sheets(db, user)


@router.post(
    "", response_model=WorkStatSheetOut, status_code=status.HTTP_201_CREATED,
    summary="新建统计表（管理员）",
)
def create_sheet(
    payload: WorkStatSheetCreate, db: DbSession, actor: AdminUser, ip: ClientIp
) -> dict:
    sheet = work_stat_service.create_sheet(db, payload, actor=actor, ip=ip)
    return work_stat_service.to_sheet_out(sheet, actor)


@router.get("/{sheet_id}", response_model=WorkStatSheetOut, summary="统计表详情")
def get_sheet(sheet_id: int, db: DbSession, user: CurrentUser) -> dict:
    sheet = work_stat_service.get_sheet_or_404(db, sheet_id, user)
    return work_stat_service.to_sheet_out(sheet, user)


@router.put("/{sheet_id}", response_model=WorkStatSheetOut, summary="修改统计表（管理员）")
def update_sheet(
    sheet_id: int,
    payload: WorkStatSheetUpdate,
    db: DbSession,
    actor: AdminUser,
    ip: ClientIp,
) -> dict:
    sheet = work_stat_service.get_sheet_or_404(db, sheet_id)
    sheet = work_stat_service.update_sheet(db, sheet, payload, actor=actor, ip=ip)
    return work_stat_service.to_sheet_out(sheet, actor)


@router.delete("/{sheet_id}", response_model=OkResp, summary="删除统计表（管理员）")
def delete_sheet(
    sheet_id: int, db: DbSession, actor: AdminUser, ip: ClientIp
) -> dict:
    sheet = work_stat_service.get_sheet_or_404(db, sheet_id)
    work_stat_service.delete_sheet(db, sheet, actor=actor, ip=ip)
    return {"ok": True}


# --------------------------------------------------------------------------- 行


@router.get("/{sheet_id}/rows", response_model=list[WorkStatRowOut], summary="行数据")
def list_rows(
    sheet_id: int,
    db: DbSession,
    user: CurrentUser,
    after_updated_at: Annotated[datetime | None, Query()] = None,
) -> list[dict]:
    sheet = work_stat_service.get_sheet_or_404(db, sheet_id, user)
    return work_stat_service.list_rows(db, sheet, after_updated_at=after_updated_at)


@router.post(
    "/{sheet_id}/rows", response_model=WorkStatRowOut,
    status_code=status.HTTP_201_CREATED, summary="新增行",
)
def create_row(
    sheet_id: int, payload: WorkStatRowCreate, db: DbSession, user: CurrentUser
) -> dict:
    sheet = work_stat_service.get_sheet_or_404(db, sheet_id, user)
    row = work_stat_service.create_row(db, sheet, payload, actor=user)
    return {
        "id": row.id, "row_no": row.row_no, "cells": row.cells,
        "version": row.version, "updated_by": row.updated_by, "updated_at": row.updated_at,
    }


@router.put("/{sheet_id}/rows/{row_id}", response_model=WorkStatRowOut, summary="更新行")
def update_row(
    sheet_id: int,
    row_id: int,
    payload: WorkStatRowUpdate,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    sheet = work_stat_service.get_sheet_or_404(db, sheet_id, user)
    row = work_stat_service.update_row(db, sheet, row_id, payload, actor=user)
    return {
        "id": row.id, "row_no": row.row_no, "cells": row.cells,
        "version": row.version, "updated_by": row.updated_by, "updated_at": row.updated_at,
    }


@router.delete("/{sheet_id}/rows/{row_id}", response_model=OkResp, summary="删除行")
def delete_row(sheet_id: int, row_id: int, db: DbSession, user: CurrentUser) -> dict:
    sheet = work_stat_service.get_sheet_or_404(db, sheet_id, user)
    work_stat_service.delete_row(db, sheet, row_id, actor=user)
    return {"ok": True}


@router.get(
    "/{sheet_id}/rows/{row_id}/logs", response_model=list[WorkStatRowLogOut],
    summary="行修改历史",
)
def row_logs(sheet_id: int, row_id: int, db: DbSession, user: CurrentUser) -> list[dict]:
    sheet = work_stat_service.get_sheet_or_404(db, sheet_id, user)
    return work_stat_service.list_row_logs(db, sheet, row_id)


# --------------------------------------------------------------------------- Excel


@router.post(
    "/{sheet_id}/import",
    response_model=WorkStatImportResult | WorkStatImportPreview,
    summary="导入 Excel（dry_run=true 仅预览）",
)
def import_rows(
    sheet_id: int,
    db: DbSession,
    actor: AdminUser,
    ip: ClientIp,
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
) -> dict:
    sheet = work_stat_service.get_sheet_or_404(db, sheet_id)
    content = file.file.read()
    return work_stat_service.import_xlsx(
        db, sheet, content, actor=actor, dry_run=dry_run, ip=ip
    )


@router.get("/{sheet_id}/export", summary="导出 Excel")
def export_rows(sheet_id: int, db: DbSession, user: CurrentUser, ip: ClientIp) -> Response:
    sheet = work_stat_service.get_sheet_or_404(db, sheet_id, user)
    content = work_stat_service.export_xlsx(db, sheet, actor=user, ip=ip)
    filename = quote(f"{sheet.name}.xlsx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"work-stats.xlsx\"; filename*=UTF-8''{filename}"
            )
        },
    )
