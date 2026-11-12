"""共享电子表格的 DTO。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SpreadsheetScope(BaseModel):
    all: bool = False
    roles: list[str] = Field(default_factory=list)
    depts: list[int] = Field(default_factory=list)
    users: list[int] = Field(default_factory=list)


class SpreadsheetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    viewer_scope: SpreadsheetScope | None = None
    editor_scope: SpreadsheetScope | None = None


class SpreadsheetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    viewer_scope: SpreadsheetScope | None = None
    editor_scope: SpreadsheetScope | None = None


class SpreadsheetSave(BaseModel):
    snapshot: dict[str, Any]
    version: int = Field(ge=0)


class SpreadsheetOut(BaseModel):
    id: int
    name: str
    description: str | None
    version: int
    viewer_scope: SpreadsheetScope | None
    editor_scope: SpreadsheetScope | None
    can_edit: bool
    created_by: int
    created_by_name: str | None = None
    updated_by: int | None = None
    updated_by_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SpreadsheetDetailOut(SpreadsheetOut):
    snapshot: dict[str, Any] | None = None


class SpreadsheetStateOut(BaseModel):
    version: int
    changed: bool
    snapshot: dict[str, Any] | None = None
    updated_by: int | None = None
    updated_by_name: str | None = None
    updated_at: datetime | None = None
