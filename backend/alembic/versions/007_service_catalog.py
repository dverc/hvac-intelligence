"""service_catalog table

Revision ID: 007_service_catalog
Revises: 006_add_org_id
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_service_catalog"
down_revision: Union[str, None] = "006_add_org_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_catalog",
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("service_code", sa.String(length=100), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_price_usd", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("price_max_usd", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("price_notes", sa.String(length=500), nullable=True),
        sa.Column("duration_minutes_min", sa.Integer(), nullable=True),
        sa.Column("duration_minutes_max", sa.Integer(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("requires_equipment_type", sa.String(length=100), nullable=True),
        sa.Column(
            "emergency_surcharge_pct",
            sa.Numeric(precision=5, scale=2),
            server_default="0",
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.org_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("service_id"),
        sa.UniqueConstraint("org_id", "service_code", name="uq_service_catalog_org_code"),
    )
    op.create_index(
        "idx_service_catalog_org_category",
        "service_catalog",
        ["org_id", "category"],
    )
    op.create_index(
        "idx_service_catalog_org_active",
        "service_catalog",
        ["org_id", "is_active"],
    )
    op.create_index(
        op.f("ix_service_catalog_org_id"), "service_catalog", ["org_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_service_catalog_org_id"), table_name="service_catalog")
    op.drop_index("idx_service_catalog_org_active", table_name="service_catalog")
    op.drop_index("idx_service_catalog_org_category", table_name="service_catalog")
    op.drop_table("service_catalog")
