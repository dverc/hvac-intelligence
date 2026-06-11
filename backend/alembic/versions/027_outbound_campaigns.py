"""outbound campaign compliance tables

Revision ID: 027_outbound_campaigns
Revises: 026_ground_truth_labels
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "027_outbound_campaigns"
down_revision: Union[str, None] = "026_ground_truth_labels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consent_records",
        sa.Column(
            "consent_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("consent_given", sa.Boolean(), nullable=False),
        sa.Column("consent_method", sa.String(length=32), nullable=False),
        sa.Column("consent_call_id", sa.String(length=128), nullable=True),
        sa.Column("consent_text", sa.Text(), nullable=False),
        sa.Column(
            "consented_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_method", sa.String(length=32), nullable=True),
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
        "idx_consent_records_customer_type",
        "consent_records",
        ["customer_id", "consent_type", "revoked_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_consent_records_org_id"),
        "consent_records",
        ["org_id"],
        unique=False,
    )

    op.create_table(
        "outbound_campaigns",
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_name", sa.String(length=255), nullable=False),
        sa.Column("campaign_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column(
            "churn_score_threshold",
            sa.Numeric(4, 3),
            nullable=False,
            server_default="0.750",
        ),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("calling_hours_start", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("calling_hours_end", sa.Integer(), nullable=False, server_default="18"),
        sa.Column(
            "disclosure_style",
            sa.String(length=16),
            nullable=False,
            server_default="FRIENDLY",
        ),
        sa.Column(
            "total_customers_targeted",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("total_calls_made", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_consented", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_booked", sa.Integer(), nullable=False, server_default="0"),
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
            ["org_id"],
            ["organizations.org_id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        op.f("ix_outbound_campaigns_org_id"),
        "outbound_campaigns",
        ["org_id"],
        unique=False,
    )
    op.create_index(
        "idx_outbound_campaigns_org_status",
        "outbound_campaigns",
        ["org_id", "status"],
        unique=False,
    )

    op.create_table(
        "outbound_call_attempts",
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("vapi_call_id", sa.String(length=128), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column(
            "disclosure_delivered",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "consent_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["outbound_campaigns.campaign_id"],
            ondelete="CASCADE",
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
        "idx_outbound_attempts_campaign",
        "outbound_call_attempts",
        ["campaign_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_outbound_attempts_customer_created",
        "outbound_call_attempts",
        ["customer_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_call_attempts_org_id"),
        "outbound_call_attempts",
        ["org_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_outbound_call_attempts_org_id"),
        table_name="outbound_call_attempts",
    )
    op.drop_index(
        "idx_outbound_attempts_customer_created",
        table_name="outbound_call_attempts",
    )
    op.drop_index(
        "idx_outbound_attempts_campaign",
        table_name="outbound_call_attempts",
    )
    op.drop_table("outbound_call_attempts")
    op.drop_index("idx_outbound_campaigns_org_status", table_name="outbound_campaigns")
    op.drop_index(op.f("ix_outbound_campaigns_org_id"), table_name="outbound_campaigns")
    op.drop_table("outbound_campaigns")
    op.drop_index(op.f("ix_consent_records_org_id"), table_name="consent_records")
    op.drop_index("idx_consent_records_customer_type", table_name="consent_records")
    op.drop_table("consent_records")
