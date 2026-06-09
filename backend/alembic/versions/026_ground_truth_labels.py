"""ground_truth_labels table for churn model evaluation

Revision ID: 026_ground_truth_labels
Revises: 025_user_lockout_fields
Create Date: 2026-06-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "026_ground_truth_labels"
down_revision: Union[str, None] = "025_user_lockout_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ground_truth_labels",
        sa.Column(
            "label_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("churned", sa.Boolean(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "feature_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("churn_probability_at_time", sa.Numeric(4, 3), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.customer_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.org_id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        op.f("ix_ground_truth_labels_customer_id"),
        "ground_truth_labels",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ground_truth_labels_org_id"),
        "ground_truth_labels",
        ["org_id"],
        unique=False,
    )
    op.create_index(
        "idx_ground_truth_labels_org_recorded_at",
        "ground_truth_labels",
        ["org_id", "recorded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_ground_truth_labels_org_recorded_at", table_name="ground_truth_labels"
    )
    op.drop_index(
        op.f("ix_ground_truth_labels_org_id"), table_name="ground_truth_labels"
    )
    op.drop_index(
        op.f("ix_ground_truth_labels_customer_id"), table_name="ground_truth_labels"
    )
    op.drop_table("ground_truth_labels")
