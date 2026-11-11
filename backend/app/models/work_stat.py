"""工作量统计（M12）。

独立于审批数据：一张表 = 一组固定列 + 多行人工填写的数据。
多人协同靠行级 version 乐观锁，不做单元格锁。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import WorkStatSheetStatus
from app.db.base import Base, CreatedAtMixin, IntType, PkMixin, TimestampMixin


class WorkStatSheet(Base, PkMixin, TimestampMixin):
    """统计表定义：名称、固定列、可见/可编辑范围。"""

    __tablename__ = "work_stat_sheets"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: [{key,label,type,width,required,options}]
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    #: {"roles": [code], "depts": [id], "users": [id]}；None = 全体可见
    viewer_scope: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: 同上；None = 仅管理员可编辑
    editor_scope: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=WorkStatSheetStatus.ACTIVE, index=True
    )
    created_by: Mapped[int] = mapped_column(IntType, ForeignKey("users.id"), nullable=False)

    rows: Mapped[list[WorkStatRow]] = relationship(
        "WorkStatRow", back_populates="sheet", cascade="all, delete-orphan",
        order_by="WorkStatRow.row_no",
    )


class WorkStatRow(Base, PkMixin, TimestampMixin):
    """一行数据。cells 以列 key 为键，只存列定义里存在的键。"""

    __tablename__ = "work_stat_rows"

    sheet_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("work_stat_sheets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    cells: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    #: 乐观锁：更新时必须带客户端持有的版本
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int | None] = mapped_column(IntType, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(IntType, nullable=True)

    sheet: Mapped[WorkStatSheet] = relationship("WorkStatSheet", back_populates="rows")


class WorkStatRowLog(Base, PkMixin, CreatedAtMixin):
    """行级修改留痕；行删除后日志仍保留，所以不建外键。"""

    __tablename__ = "work_stat_row_logs"

    sheet_id: Mapped[int] = mapped_column(IntType, nullable=False, index=True)
    row_id: Mapped[int] = mapped_column(IntType, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    actor_id: Mapped[int] = mapped_column(IntType, nullable=False)
