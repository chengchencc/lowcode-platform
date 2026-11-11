"""M12：工作量统计（协作表格）

Revision ID: 0005_m_work_stats
Revises: 0004_m_auto_number
Create Date: 2026-11-11

- work_stat_sheets     统计表定义（固定列 + 可见/可编辑范围）
- work_stat_rows       行数据，行级 version 乐观锁
- work_stat_row_logs   行级修改留痕（行删除后保留，不建外键）
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_m_work_stats"
down_revision: str | None = "0004_m_auto_number"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "work_stat_sheets",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("viewer_scope", sa.JSON(), nullable=True),
        sa.Column("editor_scope", sa.JSON(), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", BIGINT, nullable=False),
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_stat_sheets_status", "work_stat_sheets", ["status"])

    op.create_table(
        "work_stat_rows",
        sa.Column("sheet_id", BIGINT, nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("cells", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", BIGINT, nullable=True),
        sa.Column("updated_by", BIGINT, nullable=True),
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["sheet_id"], ["work_stat_sheets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_stat_rows_sheet_id", "work_stat_rows", ["sheet_id"])
    op.create_index("ix_work_stat_rows_sheet_row", "work_stat_rows", ["sheet_id", "row_no"])
    op.create_index("ix_work_stat_rows_sheet_updated", "work_stat_rows", ["sheet_id", "updated_at"])

    op.create_table(
        "work_stat_row_logs",
        sa.Column("sheet_id", BIGINT, nullable=False),
        sa.Column("row_id", BIGINT, nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("actor_id", BIGINT, nullable=False),
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_stat_row_logs_sheet_id", "work_stat_row_logs", ["sheet_id"])
    op.create_index("ix_work_stat_row_logs_row_id", "work_stat_row_logs", ["row_id"])


def downgrade() -> None:
    op.drop_index("ix_work_stat_row_logs_row_id", table_name="work_stat_row_logs")
    op.drop_index("ix_work_stat_row_logs_sheet_id", table_name="work_stat_row_logs")
    op.drop_table("work_stat_row_logs")
    op.drop_index("ix_work_stat_rows_sheet_updated", table_name="work_stat_rows")
    op.drop_index("ix_work_stat_rows_sheet_row", table_name="work_stat_rows")
    op.drop_index("ix_work_stat_rows_sheet_id", table_name="work_stat_rows")
    op.drop_table("work_stat_rows")
    op.drop_index("ix_work_stat_sheets_status", table_name="work_stat_sheets")
    op.drop_table("work_stat_sheets")
