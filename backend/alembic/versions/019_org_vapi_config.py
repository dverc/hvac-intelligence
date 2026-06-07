"""add per-org Vapi assistant configuration columns

Revision ID: 019_org_vapi_config
Revises: 018_audit_log
Create Date: 2026-06-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_org_vapi_config"
down_revision: Union[str, None] = "018_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "organizations",
        "vapi_assistant_id",
        existing_type=sa.String(length=128),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.add_column(
        "organizations",
        sa.Column("vapi_phone_number", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("agent_name", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "agent_name")
    op.drop_column("organizations", "vapi_phone_number")
    op.alter_column(
        "organizations",
        "vapi_assistant_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=128),
        existing_nullable=True,
    )
