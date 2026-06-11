"""org_settings table for multi-tenant onboarding

Revision ID: 028_org_settings
Revises: 027_outbound_campaigns
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "028_org_settings"
down_revision: Union[str, None] = "027_outbound_campaigns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_settings",
        sa.Column(
            "setting_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("phone_display", sa.String(length=20), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("zip", sa.String(length=20), nullable=True),
        sa.Column("agent_greeting", sa.Text(), nullable=True),
        sa.Column(
            "agent_name",
            sa.String(length=100),
            nullable=False,
            server_default="AI Assistant",
        ),
        sa.Column(
            "business_hours_start",
            sa.Integer(),
            nullable=False,
            server_default="8",
        ),
        sa.Column(
            "business_hours_end",
            sa.Integer(),
            nullable=False,
            server_default="18",
        ),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="America/Los_Angeles",
        ),
        sa.Column("vapi_assistant_id", sa.String(length=255), nullable=True),
        sa.Column("vapi_phone_number_id", sa.String(length=128), nullable=True),
        sa.Column("vapi_phone_number", sa.String(length=50), nullable=True),
        sa.Column(
            "outbound_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "outbound_disclosure_style",
            sa.String(length=16),
            nullable=False,
            server_default="FRIENDLY",
        ),
        sa.Column(
            "max_outbound_attempts",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
        sa.Column(
            "onboarding_completed",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "onboarding_step",
            sa.Integer(),
            nullable=False,
            server_default="0",
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
            ["org_id"],
            ["organizations.org_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("org_id", name="uq_org_settings_org_id"),
    )
    op.create_index(
        op.f("ix_org_settings_org_id"), "org_settings", ["org_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_org_settings_org_id"), table_name="org_settings")
    op.drop_table("org_settings")
