"""add appointment reminder timestamps to dispatch_jobs

Revision ID: 021_dispatch_reminder_fields
Revises: 020_technician_external_id
Create Date: 2026-06-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_dispatch_reminder_fields"
down_revision: Union[str, None] = "020_technician_external_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dispatch_jobs",
        sa.Column("reminder_24h_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dispatch_jobs",
        sa.Column("reminder_1h_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dispatch_jobs", "reminder_1h_sent_at")
    op.drop_column("dispatch_jobs", "reminder_24h_sent_at")
