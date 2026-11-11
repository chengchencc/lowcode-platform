"""工作量统计的 DTO（M12）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class WorkStatColumn(BaseModel):
    key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
    label: str = Field(min_length=1, max_length=64)
    type: Literal["text", "number", "date", "select"]
    width: int = Field(default=120, ge=60, le=400)
    required: bool = False
    options: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_options(self) -> WorkStatColumn:
        if self.type == "select" and not self.options:
            raise ValueError("下拉列必须配置选项")
        if self.type != "select" and self.options:
            raise ValueError("只有下拉列可以配置选项")
        return self


class WorkStatScope(BaseModel):
    """空对象/None 的含义由 service 决定：viewer None=全体，editor None=仅管理员。"""

    roles: list[str] = Field(default_factory=list)
    depts: list[int] = Field(default_factory=list)
    users: list[int] = Field(default_factory=list)


class WorkStatSheetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    columns: list[WorkStatColumn] = Field(min_length=1, max_length=50)
    viewer_scope: WorkStatScope | None = None
    editor_scope: WorkStatScope | None = None
    sort: int = 0


class WorkStatSheetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    columns: list[WorkStatColumn] | None = Field(default=None, min_length=1, max_length=50)
    viewer_scope: WorkStatScope | None = None
    editor_scope: WorkStatScope | None = None
    sort: int | None = None
    status: Literal["ACTIVE", "DISABLED"] | None = None


class WorkStatSheetOut(BaseModel):
    id: int
    name: str
    description: str | None
    columns: list[WorkStatColumn]
    viewer_scope: WorkStatScope | None
    editor_scope: WorkStatScope | None
    sort: int
    status: str
    can_edit: bool
    created_by: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkStatRowOut(BaseModel):
    id: int
    row_no: int
    cells: dict[str, Any]
    version: int
    updated_by: int | None = None
    updated_at: datetime | None = None


class WorkStatRowCreate(BaseModel):
    cells: dict[str, Any] = Field(default_factory=dict)


class WorkStatRowUpdate(BaseModel):
    cells: dict[str, Any]
    version: int = Field(ge=0)


class WorkStatImportPreview(BaseModel):
    headers: list[str]
    preview_rows: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    total_rows: int


class WorkStatImportResult(BaseModel):
    imported: int
    skipped: int = 0


class WorkStatRowLogOut(BaseModel):
    id: int
    action: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    actor_id: int
    actor_name: str | None = None
    created_at: datetime | None = None
