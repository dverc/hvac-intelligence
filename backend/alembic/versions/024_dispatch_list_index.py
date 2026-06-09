"""add composite index for dispatch jobs list query

Revision ID: 024_dispatch_list_index
Revises: 023_users_table
Create Date: 2026-06-08

017_performance_indexes.py adds idx_dispatch_jobs_scheduled_window_start on
(scheduled_window_start) only. This migration adds the composite
(org_id, scheduled_window_start) index used by list_scheduled_jobs.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "024_dispatch_list_index"
down_revision: Union[str, None] = "023_users_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dispatch_jobs_org_scheduled_window_start
        ON dispatch_jobs (org_id, scheduled_window_start)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_dispatch_jobs_org_scheduled_window_start")
