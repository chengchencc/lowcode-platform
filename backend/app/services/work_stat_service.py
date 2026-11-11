"""工作量统计（M12）。

独立于审批数据。协作模型：行级 `version` 乐观锁 + 客户端 5 秒增量拉取；
同一行先保存者生效，后保存者收到 409 后刷新重试。
"""

from __future__ import annotations

import io
from datetime import UTC, date, datetime
from typing import Any

from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import AuditAction, AuditBizType, WorkStatSheetStatus
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.core.policy import is_admin
from app.models import User, WorkStatRow, WorkStatRowLog, WorkStatSheet
from app.schemas.work_stat import (
    WorkStatColumn,
    WorkStatRowCreate,
    WorkStatRowUpdate,
    WorkStatSheetCreate,
    WorkStatSheetUpdate,
)
from app.services import audit_service

MAX_ROWS = 2000
MAX_IMPORT_ROWS = 2000


# --------------------------------------------------------------------------- 权限与输出


def _scope_match(scope: dict[str, Any] | None, user: User) -> bool:
    if not scope:
        return False
    if user.id in (scope.get("users") or []):
        return True
    if user.dept_id is not None and user.dept_id in (scope.get("depts") or []):
        return True
    roles = scope.get("roles") or []
    return bool(roles) and user.has_role(*roles)


def can_view(sheet: WorkStatSheet, user: User) -> bool:
    if is_admin(user):
        return True
    return sheet.viewer_scope is None or _scope_match(sheet.viewer_scope, user)


def can_edit(sheet: WorkStatSheet, user: User) -> bool:
    if is_admin(user):
        return True
    return sheet.editor_scope is not None and _scope_match(sheet.editor_scope, user)


def _scope_dict(scope) -> dict[str, Any] | None:
    return scope.model_dump() if scope is not None else None


def to_sheet_out(sheet: WorkStatSheet, user: User) -> dict[str, Any]:
    return {
        "id": sheet.id,
        "name": sheet.name,
        "description": sheet.description,
        "columns": sheet.columns or [],
        "viewer_scope": sheet.viewer_scope,
        "editor_scope": sheet.editor_scope,
        "sort": sheet.sort,
        "status": sheet.status,
        "can_edit": can_edit(sheet, user),
        "created_by": sheet.created_by,
        "created_at": sheet.created_at,
        "updated_at": sheet.updated_at,
    }


def list_sheets(db: Session, user: User) -> list[dict[str, Any]]:
    stmt = select(WorkStatSheet)
    if not is_admin(user):
        stmt = stmt.where(WorkStatSheet.status == WorkStatSheetStatus.ACTIVE)
    sheets = list(db.scalars(stmt.order_by(WorkStatSheet.sort, WorkStatSheet.id)).all())
    return [to_sheet_out(sheet, user) for sheet in sheets if can_view(sheet, user)]


def get_sheet_or_404(db: Session, sheet_id: int, user: User | None = None) -> WorkStatSheet:
    sheet = db.get(WorkStatSheet, sheet_id)
    if sheet is None:
        raise NotFoundError("统计表不存在", code="WORK_STAT_SHEET_NOT_FOUND")
    # 非管理员看不到已停用的表；管理员要能进去重新启用
    if user is not None and not is_admin(user) and sheet.status != WorkStatSheetStatus.ACTIVE:
        raise NotFoundError("统计表不存在", code="WORK_STAT_SHEET_NOT_FOUND")
    if user is not None and not can_view(sheet, user):
        raise ForbiddenError("你没有权限查看该统计表", code="WORK_STAT_FORBIDDEN")
    return sheet


# --------------------------------------------------------------------------- 表定义


RESERVED_COLUMN_KEYS = {"id", "row_no", "version", "updated_at", "cells", "origin"}


def _validate_columns(columns: list[WorkStatColumn]) -> list[dict[str, Any]]:
    keys = [c.key for c in columns]
    labels = [c.label for c in columns]
    if any(key in RESERVED_COLUMN_KEYS for key in keys):
        raise UnprocessableError(
            "列 key 不能使用 id/row_no/version/updated_at/cells 等保留字",
            code="WORK_STAT_COLUMN_RESERVED",
        )
    if len(set(keys)) != len(keys):
        raise UnprocessableError("列 key 重复", code="WORK_STAT_COLUMN_DUPLICATE")
    if len(set(labels)) != len(labels):
        raise UnprocessableError("列名重复，Excel 导入按列名匹配", code="WORK_STAT_LABEL_DUPLICATE")
    return [c.model_dump() for c in columns]


def create_sheet(
    db: Session,
    payload: WorkStatSheetCreate,
    *,
    actor: User,
    ip: str | None = None,
) -> WorkStatSheet:
    sheet = WorkStatSheet(
        name=payload.name,
        description=payload.description,
        columns=_validate_columns(payload.columns),
        viewer_scope=_scope_dict(payload.viewer_scope),
        editor_scope=_scope_dict(payload.editor_scope),
        sort=payload.sort,
        status=WorkStatSheetStatus.ACTIVE,
        created_by=actor.id,
    )
    db.add(sheet)
    db.flush()
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.WORK_STAT_SHEET,
        biz_id=sheet.id,
        action=AuditAction.CREATE,
        summary=f"新建工作量统计表「{sheet.name}」",
        detail={"name": sheet.name, "columns": len(sheet.columns or [])},
        ip=ip,
    )
    db.commit()
    db.refresh(sheet)
    return sheet


def update_sheet(
    db: Session,
    sheet: WorkStatSheet,
    payload: WorkStatSheetUpdate,
    *,
    actor: User,
    ip: str | None = None,
) -> WorkStatSheet:
    if payload.name is not None:
        sheet.name = payload.name
    if "description" in payload.model_fields_set:
        sheet.description = payload.description
    if payload.columns is not None:
        sheet.columns = _validate_columns(payload.columns)
    if "viewer_scope" in payload.model_fields_set:
        sheet.viewer_scope = _scope_dict(payload.viewer_scope)
    if "editor_scope" in payload.model_fields_set:
        sheet.editor_scope = _scope_dict(payload.editor_scope)
    if payload.sort is not None:
        sheet.sort = payload.sort
    if payload.status is not None:
        sheet.status = payload.status

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.WORK_STAT_SHEET,
        biz_id=sheet.id,
        action=AuditAction.UPDATE,
        summary=f"修改工作量统计表「{sheet.name}」",
        ip=ip,
    )
    db.commit()
    db.refresh(sheet)
    return sheet


def delete_sheet(
    db: Session, sheet: WorkStatSheet, *, actor: User, ip: str | None = None
) -> None:
    biz_id, name = sheet.id, sheet.name
    db.delete(sheet)
    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.WORK_STAT_SHEET,
        biz_id=biz_id,
        action=AuditAction.DELETE,
        summary=f"删除工作量统计表「{name}」",
        ip=ip,
    )
    db.commit()


# --------------------------------------------------------------------------- 行数据


def _validate_cells(columns: list[dict[str, Any]], cells: dict[str, Any]) -> dict[str, Any]:
    defined = {column["key"]: column for column in columns}
    unknown = set(cells) - set(defined)
    if unknown:
        raise UnprocessableError(
            f"未知列：{', '.join(sorted(unknown))}", code="WORK_STAT_UNKNOWN_COLUMN"
        )

    out: dict[str, Any] = {}
    for key, column in defined.items():
        raw = cells.get(key)
        if raw is None or raw == "":
            if column.get("required"):
                raise UnprocessableError(
                    f"「{column['label']}」必填", code="WORK_STAT_REQUIRED"
                )
            out[key] = "" if column["type"] == "text" else None
            continue

        if column["type"] == "number":
            try:
                out[key] = float(raw)
            except (TypeError, ValueError) as exc:
                raise UnprocessableError(
                    f"「{column['label']}」必须是数字", code="WORK_STAT_INVALID_NUMBER"
                ) from exc
        elif column["type"] == "date":
            text = str(raw)
            try:
                datetime.strptime(text, "%Y-%m-%d")
            except ValueError as exc:
                raise UnprocessableError(
                    f"「{column['label']}」日期格式应为 YYYY-MM-DD",
                    code="WORK_STAT_INVALID_DATE",
                ) from exc
            out[key] = text
        elif column["type"] == "select":
            text = str(raw)
            if text not in (column.get("options") or []):
                raise UnprocessableError(
                    f"「{column['label']}」的值不在选项内", code="WORK_STAT_INVALID_OPTION"
                )
            out[key] = text
        else:
            out[key] = str(raw)
    return out


def list_rows(
    db: Session,
    sheet: WorkStatSheet,
    *,
    after_updated_at: datetime | None = None,
) -> list[dict[str, Any]]:
    stmt = select(WorkStatRow).where(WorkStatRow.sheet_id == sheet.id)
    if after_updated_at is not None:
        if after_updated_at.tzinfo is not None:
            after_updated_at = after_updated_at.astimezone(UTC).replace(tzinfo=None)
        stmt = stmt.where(WorkStatRow.updated_at > after_updated_at)
    rows = list(db.scalars(stmt.order_by(WorkStatRow.row_no, WorkStatRow.id)).all())
    return [
        {
            "id": row.id,
            "row_no": row.row_no,
            "cells": row.cells,
            "version": row.version,
            "updated_by": row.updated_by,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def _next_row_no(db: Session, sheet_id: int) -> int:
    latest = db.scalar(
        select(func.max(WorkStatRow.row_no)).where(WorkStatRow.sheet_id == sheet_id)
    )
    return (latest or 0) + 1


def _log(
    db: Session,
    *,
    sheet: WorkStatSheet,
    row_id: int,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actor: User,
) -> None:
    db.add(
        WorkStatRowLog(
            sheet_id=sheet.id,
            row_id=row_id,
            action=action,
            before=before,
            after=after,
            actor_id=actor.id,
        )
    )


def create_row(
    db: Session,
    sheet: WorkStatSheet,
    payload: WorkStatRowCreate,
    *,
    actor: User,
) -> WorkStatRow:
    if not can_edit(sheet, actor):
        raise ForbiddenError("你没有编辑该统计表的权限", code="WORK_STAT_EDIT_FORBIDDEN")

    total = db.scalar(
        select(func.count(WorkStatRow.id)).where(WorkStatRow.sheet_id == sheet.id)
    ) or 0
    if total >= MAX_ROWS:
        raise UnprocessableError(f"单表最多 {MAX_ROWS} 行", code="WORK_STAT_ROW_LIMIT")

    cells = _validate_cells(sheet.columns or [], payload.cells)
    row = WorkStatRow(
        sheet_id=sheet.id,
        row_no=_next_row_no(db, sheet.id),
        cells=cells,
        version=0,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(row)
    db.flush()
    _log(db, sheet=sheet, row_id=row.id, action="CREATE", before=None, after=cells, actor=actor)
    db.commit()
    db.refresh(row)
    return row


def _get_row_or_404(db: Session, sheet: WorkStatSheet, row_id: int) -> WorkStatRow:
    row = db.get(WorkStatRow, row_id)
    if row is None or row.sheet_id != sheet.id:
        raise NotFoundError("数据行不存在", code="WORK_STAT_ROW_NOT_FOUND")
    return row


def update_row(
    db: Session,
    sheet: WorkStatSheet,
    row_id: int,
    payload: WorkStatRowUpdate,
    *,
    actor: User,
) -> WorkStatRow:
    if not can_edit(sheet, actor):
        raise ForbiddenError("你没有编辑该统计表的权限", code="WORK_STAT_EDIT_FORBIDDEN")

    row = _get_row_or_404(db, sheet, row_id)
    if row.version != payload.version:
        raise ConflictError("该行已被他人修改，请刷新后重试", code="WORK_STAT_ROW_CONFLICT")

    cells = _validate_cells(sheet.columns or [], payload.cells)
    before = dict(row.cells or {})
    row.cells = cells
    row.version += 1
    row.updated_by = actor.id
    _log(db, sheet=sheet, row_id=row.id, action="UPDATE", before=before, after=cells, actor=actor)
    db.commit()
    db.refresh(row)
    return row


def delete_row(db: Session, sheet: WorkStatSheet, row_id: int, *, actor: User) -> None:
    if not can_edit(sheet, actor):
        raise ForbiddenError("你没有编辑该统计表的权限", code="WORK_STAT_EDIT_FORBIDDEN")
    row = _get_row_or_404(db, sheet, row_id)
    _log(
        db, sheet=sheet, row_id=row.id, action="DELETE",
        before=dict(row.cells or {}), after=None, actor=actor,
    )
    db.delete(row)
    db.commit()


def list_row_logs(db: Session, sheet: WorkStatSheet, row_id: int) -> list[dict[str, Any]]:
    _get_row_or_404(db, sheet, row_id)
    logs = list(
        db.scalars(
            select(WorkStatRowLog)
            .where(WorkStatRowLog.row_id == row_id)
            .order_by(WorkStatRowLog.id.desc())
        ).all()
    )
    actor_ids = {log.actor_id for log in logs}
    names = {
        user.id: user.real_name
        for user in db.scalars(select(User).where(User.id.in_(actor_ids))).all()
    } if actor_ids else {}
    return [
        {
            "id": log.id,
            "action": log.action,
            "before": log.before,
            "after": log.after,
            "actor_id": log.actor_id,
            "actor_name": names.get(log.actor_id),
            "created_at": log.created_at,
        }
        for log in logs
    ]


# --------------------------------------------------------------------------- Excel


def _cell_value(value: Any, column: dict[str, Any]) -> Any:
    if value is None:
        return None
    if column["type"] == "date" and isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    if column["type"] == "number" and isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def parse_xlsx(
    content: bytes,
    columns: list[dict[str, Any]],
    *,
    preview_size: int = 20,
) -> tuple[list[str], list[dict[str, Any]], list[str], int]:
    """返回（原始表头、前 N 行映射结果、警告、总行数）。"""
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - openpyxl 的异常类型不稳定
        raise UnprocessableError("无法解析 Excel 文件", code="WORK_STAT_IMPORT_INVALID") from exc

    sheet = workbook.active
    first_row = next(sheet.iter_rows(min_row=1, max_row=1), None)
    if first_row is None:
        raise UnprocessableError("Excel 是空表", code="WORK_STAT_IMPORT_HEADERS")
    headers = [str(cell.value).strip() if cell.value is not None else "" for cell in first_row]
    label_to_key = {column["label"]: column["key"] for column in columns}
    key_to_column = {column["key"]: column for column in columns}
    matched = {idx: label_to_key[label] for idx, label in enumerate(headers) if label in label_to_key}
    if not matched:
        raise UnprocessableError(
            "Excel 表头与统计表列名没有匹配项", code="WORK_STAT_IMPORT_HEADERS"
        )
    warnings = [f"未识别的列：{label}" for label in headers if label and label not in label_to_key]

    preview: list[dict[str, Any]] = []
    total = 0
    for row_index, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        values = list(row)
        if not any(value not in (None, "") for value in values):
            continue
        cells = {
            key: _cell_value(values[idx] if idx < len(values) else None, key_to_column[key])
            for idx, key in matched.items()
        }
        try:
            _validate_cells(columns, cells)
        except UnprocessableError as exc:
            raise UnprocessableError(f"第 {row_index} 行：{exc.message}", code=exc.code) from exc
        total += 1
        if len(preview) < preview_size:
            preview.append(cells)
    return headers, preview, warnings, total


def import_xlsx(
    db: Session,
    sheet: WorkStatSheet,
    content: bytes,
    *,
    actor: User,
    dry_run: bool,
    ip: str | None = None,
) -> dict[str, Any]:
    _headers, preview, warnings, total = parse_xlsx(content, sheet.columns or [])
    if dry_run:
        return {
            "headers": _headers,
            "preview_rows": preview,
            "warnings": warnings,
            "total_rows": total,
        }

    existing = db.scalar(
        select(func.count(WorkStatRow.id)).where(WorkStatRow.sheet_id == sheet.id)
    ) or 0
    if existing + total > MAX_ROWS:
        raise UnprocessableError(
            f"导入后超过单表 {MAX_ROWS} 行上限", code="WORK_STAT_ROW_LIMIT"
        )
    if total > MAX_IMPORT_ROWS:
        raise UnprocessableError(
            f"单次最多导入 {MAX_IMPORT_ROWS} 行", code="WORK_STAT_IMPORT_LIMIT"
        )

    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    data_sheet = workbook.active
    first_row = next(data_sheet.iter_rows(min_row=1, max_row=1), None)
    if first_row is None:
        raise UnprocessableError("Excel 是空表", code="WORK_STAT_IMPORT_HEADERS")
    headers = [str(cell.value).strip() if cell.value is not None else "" for cell in first_row]
    label_to_key = {column["label"]: column["key"] for column in (sheet.columns or [])}
    key_to_column = {column["key"]: column for column in (sheet.columns or [])}
    matched = {idx: label_to_key[label] for idx, label in enumerate(headers) if label in label_to_key}

    row_no = _next_row_no(db, sheet.id)
    imported = 0
    for row in data_sheet.iter_rows(min_row=2, values_only=True):
        values = list(row)
        if not any(value not in (None, "") for value in values):
            continue
        cells = {
            key: _cell_value(values[idx] if idx < len(values) else None, key_to_column[key])
            for idx, key in matched.items()
        }
        cells = _validate_cells(sheet.columns or [], cells)
        stat_row = WorkStatRow(
            sheet_id=sheet.id, row_no=row_no, cells=cells,
            version=0, created_by=actor.id, updated_by=actor.id,
        )
        db.add(stat_row)
        db.flush()
        _log(db, sheet=sheet, row_id=stat_row.id, action="IMPORT", before=None, after=cells, actor=actor)
        row_no += 1
        imported += 1

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.WORK_STAT_SHEET,
        biz_id=sheet.id,
        action=AuditAction.IMPORT,
        summary=f"导入工作量统计表「{sheet.name}」{imported} 行",
        detail={"imported": imported},
        ip=ip,
    )
    db.commit()
    return {"imported": imported, "skipped": 0}


def export_xlsx(
    db: Session,
    sheet: WorkStatSheet,
    *,
    actor: User,
    ip: str | None = None,
) -> bytes:
    columns = sheet.columns or []
    rows = list(
        db.scalars(
            select(WorkStatRow)
            .where(WorkStatRow.sheet_id == sheet.id)
            .order_by(WorkStatRow.row_no, WorkStatRow.id)
        ).all()
    )
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet.name[:31] or "工作量统计"
    worksheet.append([column["label"] for column in columns])
    for row in rows:
        worksheet.append([(row.cells or {}).get(column["key"]) for column in columns])
    buffer = io.BytesIO()
    workbook.save(buffer)

    audit_service.record(
        db,
        actor=actor,
        biz_type=AuditBizType.WORK_STAT_SHEET,
        biz_id=sheet.id,
        action=AuditAction.EXPORT,
        summary=f"导出工作量统计表「{sheet.name}」{len(rows)} 行",
        detail={"rows": len(rows)},
        ip=ip,
    )
    db.commit()
    return buffer.getvalue()
