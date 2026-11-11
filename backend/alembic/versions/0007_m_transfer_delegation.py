"""M14：转办与委托

Revision ID: 0007_m_transfer_delegation
Revises: 0006_m_search_tables
Create Date: 2026-11-11

- task_assignments 增加来源用户/类型/原因
- delegations 新表：委托人与被委托人、生效区间、限定流程
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_m_transfer_delegation"
down_revision: str | None = "0006_m_search_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("task_assignments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("origin_user_id", BIGINT, nullable=True))
        batch_op.add_column(sa.Column("origin_kind", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("origin_reason", sa.String(length=512), nullable=True))
        batch_op.create_index("ix_task_assignments_origin_user_id", ["origin_user_id"])

    op.create_table(
        "delegations",
        sa.Column("delegator_id", BIGINT, nullable=False),
        sa.Column("delegatee_id", BIGINT, nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("flow_template_ids", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["delegator_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["delegatee_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delegations_delegator_id", "delegations", ["delegator_id"])
    op.create_index("ix_delegations_delegatee_id", "delegations", ["delegatee_id"])
    op.create_index("ix_delegations_status", "delegations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_delegations_status", table_name="delegations")
    op.drop_index("ix_delegations_delegatee_id", table_name="delegations")
    op.drop_index("ix_delegations_delegator_id", table_name="delegations")
    op.drop_table("delegations")
    with op.batch_alter_table("task_assignments", schema=None) as batch_op:
        batch_op.drop_index("ix_task_assignments_origin_user_id")
        batch_op.drop_column("origin_reason")
        batch_op.drop_column("origin_kind")
        batch_op.drop_column("origin_user_id")
