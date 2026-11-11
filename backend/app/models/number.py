"""自动编号的已分配流水（表单字段「自动生成编号」）。"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PkMixin, TimestampMixin


class GeneratedNumber(Base, PkMixin, TimestampMixin):
    """已分配的编号。

    `number` 全局唯一：并发撞号时靠它触发唯一约束重试（与实例编号同一套路）。
    `prefix + seq_date` 决定当日流水段，`seq` 便于排查与统计。
    """

    __tablename__ = "generated_numbers"

    number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    #: YYYYMMDD（本地日期）
    seq_date: Mapped[str] = mapped_column(String(8), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
