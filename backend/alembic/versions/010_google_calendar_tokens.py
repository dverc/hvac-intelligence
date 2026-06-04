"""google_calendar_tokens table

Revision ID: 010_google_calendar_tokens
Revises: 009_scheduling_tables
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_google_calendar_tokens"
down_revision: Union[str, None] = "009_scheduling_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "google_calendar_tokens",
        sa.Column("token_id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("technician_id", sa.UUID(), nullable=True),
        sa.Column("google_account_email", sa.String(length=255), nullable=False),
        sa.Column(
            "calendar_id",
            sa.String(length=255),
            server_default="primary",
            nullable=False,
        ),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
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
        sa.ForeignKeyConstraint(
            ["technician_id"], ["technicians.technician_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("token_id"),
        sa.UniqueConstraint(
            "org_id", "google_account_email", name="uq_gcal_tokens_org_email"
        ),
    )
    op.create_index(
        op.f("ix_google_calendar_tokens_org_id"),
        "google_calendar_tokens",
        ["org_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_google_calendar_tokens_org_id"), table_name="google_calendar_tokens"
    )
    op.drop_table("google_calendar_tokens")
