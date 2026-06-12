"""Add source_call_id to ground_truth_labels for idempotent auto-labeling

Revision ID: 030_ground_truth_call_id
Revises: 029_org_settings_constraints
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030_ground_truth_call_id"
down_revision: Union[str, None] = "029_org_settings_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ground_truth_labels",
        sa.Column("source_call_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "uq_ground_truth_labels_customer_source_call",
        "ground_truth_labels",
        ["customer_id", "source_call_id"],
        unique=True,
        postgresql_where=sa.text("source_call_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ground_truth_labels_customer_source_call",
        table_name="ground_truth_labels",
    )
    op.drop_column("ground_truth_labels", "source_call_id")
