"""实例业务字段检索的 DTO（M13）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchFieldOut(BaseModel):
    field_key: str
    label: str
    field_type: str
    filter_kind: str
    options: list[Any] = Field(default_factory=list)
    start_visible: bool = False
    selected: bool = False
    indexed_at: str | None = None


class SearchFieldSaveRequest(BaseModel):
    field_keys: list[str] = Field(default_factory=list, max_length=20)


class SearchFieldSaveResult(BaseModel):
    added: int = 0
    removed: int = 0
    needs_backfill: bool = False


class SearchRebuildResult(BaseModel):
    total: int = 0
    processed: int = 0
