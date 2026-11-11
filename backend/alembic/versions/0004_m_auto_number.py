"""表单自动编号：generated_numbers

Revision ID: 0004_m_auto_number
Revises: 0003_m3_flow
Create Date: 2026-11-11

编号 = 标识位 + YYYYMMDD + 当日流水号。`number` 唯一约束用于并发撞号重试。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_m_auto_number"
down_revision: str | None = "0003_m3_flow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generated_numbers",
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=32), nullable=False),
        sa.Column("seq_date", sa.String(length=8), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number", name="ux_generated_numbers_number"),
    )
    op.create_index(
        "ix_generated_numbers_scope",
        "generated_numbers",
        ["prefix", "seq_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_generated_numbers_scope", table_name="generated_numbers")
    op.drop_table("generated_numbers")
