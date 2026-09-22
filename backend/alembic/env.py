"""Alembic 环境。

三个要点（决策 D1/D3）：
- 连接串只有一个来源：`app.core.config.settings`，与运行时完全一致。
- `render_as_batch=True`：SQLite 不支持 ALTER TABLE 改约束/删列，
  批处理模式会「建新表→拷数据→换名」，使同一份迁移在 SQLite 与 MySQL 上都能跑。
- `alembic.ini` 必须保持纯 ASCII：alembic 用 `encoding="locale"` 读它，
  中文 Windows 上是 GBK，写中文注释会在加载阶段就 UnicodeDecodeError。
  本仓库其余文件一律 UTF-8 + 中文注释，只有那个文件是例外。
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
DATABASE_URL = settings.resolve_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 不走 engine_from_config：让 URL 只经过 SQLAlchemy 的 URL 解析，
    # 绕开 alembic.ini 的 % 插值语法
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
