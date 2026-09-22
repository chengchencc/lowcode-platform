"""时间源。

统一走 naive UTC：跨 SQLite / MySQL 时 `func.now()` 的语义并不一致
（SQLite 的 CURRENT_TIMESTAMP 是 UTC，MySQL 的 NOW() 是会话时区），
若依赖数据库默认值，开发库与生产库会差 8 小时。因此时间一律由应用层生成，
存储 naive UTC，由前端负责转成本地时区展示。
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """当前 UTC 时间（naive，去掉 tzinfo 以便直接落库）。"""
    return datetime.now(UTC).replace(tzinfo=None)
