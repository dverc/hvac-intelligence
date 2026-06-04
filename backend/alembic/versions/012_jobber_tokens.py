"""jobber_tokens table

Revision ID: 012_jobber_tokens
Revises: 011_dispatch_gcal_event_id
Create Date: 2026-06-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012_jobber_tokens"
down_revision: Union[str, None] = "011_dispatch_gcal_event_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobber_tokens",
        sa.Column(
            "token_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jobber_account_id", sa.String(length=255), nullable=True),
        sa.Column("jobber_account_name", sa.String(length=255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("org_id", name="uq_jobber_tokens_org_id"),
    )
    op.create_index(
        op.f("ix_jobber_tokens_org_id"), "jobber_tokens", ["org_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_jobber_tokens_org_id"), table_name="jobber_tokens")
    op.drop_table("jobber_tokens")
