"""共享电子表格（Univer 工作簿快照）。

协同模型：近实时 + 乐观锁。
- 前端编辑后防抖保存整份 snapshot；保存携带本地 version。
- 版本不一致返回 409，由前端提示「刷新或覆盖」。
- 其他客户端每 5 秒拉取一次 state，版本变化且本地无未保存改动时重载。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.core.policy import is_admin
from app.models import SpreadsheetWorkbook, User
from app.schemas.spreadsheet import SpreadsheetCreate, SpreadsheetUpdate

MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024


def _scope_allows(scope: dict[str, Any] | None, user: User) -> bool:
    if not scope:
        return False
    if scope.get("all"):
        return True
    if user.id in (scope.get("users") or []):
        return True
    if user.dept_id is not None and user.dept_id in (scope.get("depts") or []):
        return True
    roles = scope.get("roles") or []
    return bool(roles) and user.has_role(*roles)


def can_view(workbook: SpreadsheetWorkbook, user: User) -> bool:
    if is_admin(user) or workbook.created_by == user.id:
        return True
    return _scope_allows(workbook.viewer_scope, user) or _scope_allows(
        workbook.editor_scope, user
    )


def can_edit(workbook: SpreadsheetWorkbook, user: User) -> bool:
    if is_admin(user) or workbook.created_by == user.id:
        return True
    return _scope_allows(workbook.editor_scope, user)


def can_manage(workbook: SpreadsheetWorkbook, user: User) -> bool:
    return is_admin(user) or workbook.created_by == user.id


def _user_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {
        user.id: user.real_name
        for user in db.scalars(select(User).where(User.id.in_(ids))).all()
    }


def to_out(db: Session, workbook: SpreadsheetWorkbook, user: User) -> dict[str, Any]:
    names = _user_names(db, {workbook.created_by, workbook.updated_by or 0})
    return {
        "id": workbook.id,
        "name": workbook.name,
        "description": workbook.description,
        "version": workbook.version,
        "viewer_scope": workbook.viewer_scope,
        "editor_scope": workbook.editor_scope,
        "can_edit": can_edit(workbook, user),
        "created_by": workbook.created_by,
        "created_by_name": names.get(workbook.created_by),
        "updated_by": workbook.updated_by,
        "updated_by_name": names.get(workbook.updated_by) if workbook.updated_by else None,
        "created_at": workbook.created_at,
        "updated_at": workbook.updated_at,
    }


def list_workbooks(db: Session, user: User) -> list[dict[str, Any]]:
    workbooks = list(
        db.scalars(
            select(SpreadsheetWorkbook)
            .where(SpreadsheetWorkbook.status == "ACTIVE")
            .order_by(SpreadsheetWorkbook.updated_at.desc(), SpreadsheetWorkbook.id.desc())
        ).all()
    )
    return [to_out(db, item, user) for item in workbooks if can_view(item, user)]


def get_or_404(db: Session, workbook_id: int) -> SpreadsheetWorkbook:
    workbook = db.get(SpreadsheetWorkbook, workbook_id)
    if workbook is None or workbook.status != "ACTIVE":
        raise NotFoundError("工作簿不存在", code="SPREADSHEET_NOT_FOUND")
    return workbook


def get_for_user(db: Session, workbook_id: int, user: User) -> SpreadsheetWorkbook:
    workbook = get_or_404(db, workbook_id)
    if not can_view(workbook, user):
        raise ForbiddenError("你没有权限查看该工作簿", code="SPREADSHEET_FORBIDDEN")
    return workbook


def create_workbook(
    db: Session, payload: SpreadsheetCreate, *, actor: User
) -> SpreadsheetWorkbook:
    workbook = SpreadsheetWorkbook(
        name=payload.name,
        description=payload.description,
        snapshot=None,
        version=0,
        viewer_scope=payload.viewer_scope.model_dump() if payload.viewer_scope else None,
        editor_scope=payload.editor_scope.model_dump() if payload.editor_scope else None,
        status="ACTIVE",
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(workbook)
    db.commit()
    db.refresh(workbook)
    return workbook


def update_workbook(
    db: Session, workbook: SpreadsheetWorkbook, payload: SpreadsheetUpdate, *, actor: User
) -> SpreadsheetWorkbook:
    if not can_manage(workbook, actor):
        raise ForbiddenError("只有创建者或管理员可以修改工作簿", code="SPREADSHEET_MANAGE_FORBIDDEN")
    if payload.name is not None:
        workbook.name = payload.name
    if "description" in payload.model_fields_set:
        workbook.description = payload.description
    if "viewer_scope" in payload.model_fields_set:
        workbook.viewer_scope = payload.viewer_scope.model_dump() if payload.viewer_scope else None
    if "editor_scope" in payload.model_fields_set:
        workbook.editor_scope = payload.editor_scope.model_dump() if payload.editor_scope else None
    db.commit()
    db.refresh(workbook)
    return workbook


def save_snapshot(
    db: Session,
    workbook: SpreadsheetWorkbook,
    *,
    snapshot: dict[str, Any],
    version: int,
    actor: User,
) -> dict[str, Any]:
    if not can_edit(workbook, actor):
        raise ForbiddenError("你没有编辑该工作簿的权限", code="SPREADSHEET_EDIT_FORBIDDEN")
    size = len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))
    if size > MAX_SNAPSHOT_BYTES:
        raise UnprocessableError(
            f"工作簿数据超过 {MAX_SNAPSHOT_BYTES // 1024 // 1024}MB，请拆分工作簿",
            code="SPREADSHEET_TOO_LARGE",
        )
    if version != workbook.version:
        names = _user_names(db, {workbook.updated_by or 0})
        raise ConflictError(
            "工作簿已被他人修改，请刷新或覆盖",
            code="SPREADSHEET_VERSION_CONFLICT",
            extra={
                "current_version": workbook.version,
                "updated_by_name": names.get(workbook.updated_by) if workbook.updated_by else None,
            },
        )
    workbook.snapshot = snapshot
    workbook.version += 1
    workbook.updated_by = actor.id
    db.commit()
    db.refresh(workbook)
    return {
        "version": workbook.version,
        "updated_by": workbook.updated_by,
        "updated_by_name": actor.real_name,
        "updated_at": workbook.updated_at,
    }


def state(
    db: Session,
    workbook: SpreadsheetWorkbook,
    *,
    known_version: int,
    actor: User,
) -> dict[str, Any]:
    if not can_view(workbook, actor):
        raise ForbiddenError("你没有权限查看该工作簿", code="SPREADSHEET_FORBIDDEN")
    changed = workbook.version != known_version
    names = _user_names(db, {workbook.updated_by or 0})
    return {
        "version": workbook.version,
        "changed": changed,
        "snapshot": workbook.snapshot if changed else None,
        "updated_by": workbook.updated_by,
        "updated_by_name": names.get(workbook.updated_by) if workbook.updated_by else None,
        "updated_at": workbook.updated_at,
    }


def delete_workbook(
    db: Session, workbook: SpreadsheetWorkbook, *, actor: User
) -> None:
    if not can_manage(workbook, actor):
        raise ForbiddenError("只有创建者或管理员可以删除工作簿", code="SPREADSHEET_MANAGE_FORBIDDEN")
    db.delete(workbook)
    db.commit()
