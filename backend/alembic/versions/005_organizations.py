"""organizations table + seed tenant

Revision ID: 005_organizations
Revises: 004_transcript_enrichment
Create Date: 2026-06-02

Creates the multi-tenant root table and inserts the deterministic seed
organization (SEED_ORG_ID) used to backfill all existing single-tenant rows
in migration 006.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.constants import SEED_ORG_ID_STR

revision: str = "005_organizations"
down_revision: Union[str, None] = "004_transcript_enrichment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SEED_SETTINGS = (
    '{'
    '"pinecone_namespace": "hvac-knowledge", '
    '"issue_taxonomy": ["AC_NO_COOLING", "AC_LEAKING", "FURNACE_NO_HEAT", '
    '"HEAT_PUMP_FAILURE", "MAINTENANCE", "EMERGENCY"], '
    '"customer_segments": ["residential", "commercial"], '
    '"timezone": "America/Los_Angeles"'
    '}'
)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("org_name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("industry", sa.String(length=50), nullable=False),
        sa.Column("business_phone", sa.String(length=20), nullable=True),
        sa.Column("vapi_assistant_id", sa.String(length=128), nullable=True),
        sa.Column("vapi_phone_number_id", sa.String(length=128), nullable=True),
        sa.Column(
            "plan_tier",
            sa.String(length=50),
            server_default="starter",
            nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
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
        sa.CheckConstraint(
            "industry IN ('hvac','plumbing','electrical','isp',"
            "'appliance_repair','locksmith','pest_control','other')",
            name="ck_organizations_industry",
        ),
        sa.CheckConstraint(
            "plan_tier IN ('starter','professional','enterprise')",
            name="ck_organizations_plan_tier",
        ),
        sa.PrimaryKeyConstraint("org_id"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        sa.UniqueConstraint("business_phone", name="uq_organizations_business_phone"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO organizations
                (org_id, org_name, slug, industry, business_phone,
                 vapi_assistant_id, plan_tier, is_active, settings)
            VALUES
                (:org_id, :org_name, :slug, :industry, :business_phone,
                 :vapi_assistant_id, :plan_tier, true, CAST(:settings AS JSONB))
            ON CONFLICT (org_id) DO NOTHING
            """
        ).bindparams(
            org_id=SEED_ORG_ID_STR,
            org_name="HVAC Intelligence Demo",
            slug="hvac-demo",
            industry="hvac",
            business_phone="+19498800687",
            vapi_assistant_id="4081474b-7087-41e2-bd9a-f251aeede78c",
            plan_tier="professional",
            settings=_SEED_SETTINGS,
        )
    )


def downgrade() -> None:
    op.drop_table("organizations")
