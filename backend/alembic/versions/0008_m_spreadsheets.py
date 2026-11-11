"""共享电子表格工作簿

Revision ID: 0008_m_spreadsheets
Revises: 0007_m_transfer_delegation
Create Date: 2026-11-11

Univer 工作簿快照存 JSON；version 用于近实时协同的乐观锁。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_m_spreadsheets"
down_revision: str | None = "0007_m_transfer_delegation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "spreadsheet_workbooks",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("viewer_scope", sa.JSON(), nullable=True),
        sa.Column("editor_scope", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", BIGINT, nullable=False),
        sa.Column("updated_by", BIGINT, nullable=True),
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_spreadsheet_workbooks_status", "spreadsheet_workbooks", ["status"])
    op.create_index(
        "ix_spreadsheet_workbooks_created_by", "spreadsheet_workbooks", ["created_by"]
    )


def downgrade() -> None:
    op.drop_index("ix_spreadsheet_workbooks_created_by", table_name="spreadsheet_workbooks")
    op.drop_index("ix_spreadsheet_workbooks_status", table_name="spreadsheet_workbooks")
    op.drop_table("spreadsheet_workbooks")
