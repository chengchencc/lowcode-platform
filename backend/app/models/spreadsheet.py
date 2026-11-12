"""共享电子表格工作簿。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntType, PkMixin, TimestampMixin


class SpreadsheetWorkbook(Base, PkMixin, TimestampMixin):
    """一个在线 Excel 工作簿。

    `snapshot` 是 Univer 的 `IWorkbookData` 完整快照；`version` 用于近实时协同的
    乐观锁：保存时必须带客户端持有的版本，不一致返回 409，由前端提示刷新或覆盖。
    """

    __tablename__ = "spreadsheet_workbooks"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: {"all": bool, "roles": [code], "depts": [id], "users": [id]}
    viewer_scope: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    editor_scope: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", index=True)
    created_by: Mapped[int] = mapped_column(IntType, ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(IntType, nullable=True)
