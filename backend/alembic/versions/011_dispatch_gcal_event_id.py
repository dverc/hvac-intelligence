"""add google_calendar_event_id to dispatch_jobs

Revision ID: 011_dispatch_gcal_event_id
Revises: 010_google_calendar_tokens
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_dispatch_gcal_event_id"
down_revision: Union[str, None] = "010_google_calendar_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dispatch_jobs",
        sa.Column("google_calendar_event_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dispatch_jobs", "google_calendar_event_id")
