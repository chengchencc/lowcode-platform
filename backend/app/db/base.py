"""声明式基类与可移植的列类型 / mixin。

可移植性是本模块存在的唯一理由（决策 D1）：同一份模型要能落在 SQLite（开发）
与 MySQL 8（PRD §6 目标）上，因此不得出现任何方言专有的 DDL 写法。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.clock import utcnow

#: 自增主键类型。
#: MySQL 上生成 `BIGINT`；SQLite 必须落到 `INTEGER` 才能作为 rowid 自增，
#: 否则 `INTEGER PRIMARY KEY AUTOINCREMENT` 语义丢失。
IntType = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class PkMixin:
    """自增主键。"""

    id: Mapped[int] = mapped_column(IntType, primary_key=True, autoincrement=True)


class TimestampMixin:
    """创建/更新时间。

    时间由应用层生成（见 `core/clock.py`），不用数据库默认值 —— 因为
    SQLite 的 `CURRENT_TIMESTAMP` 是 UTC 而 MySQL 的 `NOW()` 是会话时区，
    依赖数据库会让开发库与生产库差 8 小时。
    """

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class CreatedAtMixin:
    """仅创建时间。用于纯追加写的表（审计、快照、动作），这些表不应有 updated_at。"""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
