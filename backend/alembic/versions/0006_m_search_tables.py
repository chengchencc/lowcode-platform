"""M13：实例业务字段检索索引

Revision ID: 0006_m_search_tables
Revises: 0005_m_work_stats
Create Date: 2026-11-11

- form_search_fields   表单模板级「可检索字段」配置
- instance_field_values  实例 × 字段值索引（可重建的派生读模型）
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_m_search_tables"
down_revision: str | None = "0005_m_work_stats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "form_search_fields",
        sa.Column("form_template_id", BIGINT, nullable=False),
        sa.Column("field_key", sa.String(length=64), nullable=False),
        sa.Column("field_type", sa.String(length=24), nullable=False),
        sa.Column("filter_kind", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("start_visible", sa.Boolean(), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", BIGINT, nullable=False),
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["form_template_id"], ["form_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("form_template_id", "field_key", name="uk_fsf_template_field"),
    )
    op.create_index("ix_form_search_fields_form_template_id", "form_search_fields", ["form_template_id"])

    op.create_table(
        "instance_field_values",
        sa.Column("instance_id", BIGINT, nullable=False),
        sa.Column("field_key", sa.String(length=64), nullable=False),
        sa.Column("value_kind", sa.String(length=16), nullable=False),
        sa.Column("value_text", sa.String(length=512), nullable=True),
        sa.Column("value_num", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("value_index", sa.SmallInteger(), nullable=False),
        sa.Column("id", BIGINT, autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["flow_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instance_id", "field_key", "value_index", name="uk_ifv_instance_field_idx"
        ),
    )
    op.create_index("ix_instance_field_values_instance_id", "instance_field_values", ["instance_id"])
    op.create_index(
        "ix_ifv_field_text", "instance_field_values", ["field_key", "value_text", "instance_id"]
    )
    op.create_index(
        "ix_ifv_field_num", "instance_field_values", ["field_key", "value_num", "instance_id"]
    )
    op.create_index(
        "ix_ifv_field_kind", "instance_field_values", ["field_key", "value_kind", "instance_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ifv_field_kind", table_name="instance_field_values")
    op.drop_index("ix_ifv_field_num", table_name="instance_field_values")
    op.drop_index("ix_ifv_field_text", table_name="instance_field_values")
    op.drop_index("ix_instance_field_values_instance_id", table_name="instance_field_values")
    op.drop_table("instance_field_values")
    op.drop_index("ix_form_search_fields_form_template_id", table_name="form_search_fields")
    op.drop_table("form_search_fields")
