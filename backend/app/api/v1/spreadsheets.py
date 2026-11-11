"""共享电子表格接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbSession
from app.schemas.common import OkResp
from app.schemas.spreadsheet import (
    SpreadsheetCreate,
    SpreadsheetDetailOut,
    SpreadsheetOut,
    SpreadsheetSave,
    SpreadsheetStateOut,
    SpreadsheetUpdate,
)
from app.services import spreadsheet_service

router = APIRouter(prefix="/spreadsheet-workbooks", tags=["共享表格"])


@router.get("", response_model=list[SpreadsheetOut], summary="我可见的工作簿")
def list_workbooks(db: DbSession, user: CurrentUser) -> list[dict]:
    return spreadsheet_service.list_workbooks(db, user)


@router.post(
    "", response_model=SpreadsheetOut, status_code=status.HTTP_201_CREATED,
    summary="新建工作簿",
)
def create_workbook(
    payload: SpreadsheetCreate, db: DbSession, user: CurrentUser
) -> dict:
    workbook = spreadsheet_service.create_workbook(db, payload, actor=user)
    return spreadsheet_service.to_out(db, workbook, user)


@router.get("/{workbook_id}", response_model=SpreadsheetDetailOut, summary="工作簿详情")
def get_workbook(workbook_id: int, db: DbSession, user: CurrentUser) -> dict:
    workbook = spreadsheet_service.get_for_user(db, workbook_id, user)
    return {
        **spreadsheet_service.to_out(db, workbook, user),
        "snapshot": workbook.snapshot,
    }


@router.put("/{workbook_id}", response_model=SpreadsheetOut, summary="修改名称/说明/共享范围")
def update_workbook(
    workbook_id: int,
    payload: SpreadsheetUpdate,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    workbook = spreadsheet_service.get_for_user(db, workbook_id, user)
    workbook = spreadsheet_service.update_workbook(db, workbook, payload, actor=user)
    return spreadsheet_service.to_out(db, workbook, user)


@router.post("/{workbook_id}/save", summary="保存快照（乐观锁）")
def save_workbook(
    workbook_id: int,
    payload: SpreadsheetSave,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    workbook = spreadsheet_service.get_for_user(db, workbook_id, user)
    return spreadsheet_service.save_snapshot(
        db,
        workbook,
        snapshot=payload.snapshot,
        version=payload.version,
        actor=user,
    )


@router.get("/{workbook_id}/state", response_model=SpreadsheetStateOut, summary="轮询最新状态")
def workbook_state(
    workbook_id: int,
    db: DbSession,
    user: CurrentUser,
    known_version: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    workbook = spreadsheet_service.get_for_user(db, workbook_id, user)
    return spreadsheet_service.state(
        db, workbook, known_version=known_version, actor=user
    )


@router.delete("/{workbook_id}", response_model=OkResp, summary="删除工作簿")
def delete_workbook(workbook_id: int, db: DbSession, user: CurrentUser) -> dict:
    workbook = spreadsheet_service.get_for_user(db, workbook_id, user)
    spreadsheet_service.delete_workbook(db, workbook, actor=user)
    return {"ok": True}
