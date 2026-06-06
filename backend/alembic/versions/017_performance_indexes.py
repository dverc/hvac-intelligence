"""add performance indexes for hot query paths

Revision ID: 017_performance_indexes
Revises: 016_technician_skills
Create Date: 2026-06-05
"""

from typing import Sequence, Union

from alembic import op

revision: str = "017_performance_indexes"
down_revision: Union[str, None] = "016_technician_skills"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customers_org_phone
        ON customers (org_id, phone_primary)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_customers_org_churn_risk
        ON customers (org_id, ((metadata->>'churn_tier')))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dispatch_jobs_org_status
        ON dispatch_jobs (org_id, job_status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dispatch_jobs_org_customer
        ON dispatch_jobs (org_id, customer_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dispatch_jobs_scheduled_window_start
        ON dispatch_jobs (scheduled_window_start)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_call_transcripts_org_call_id
        ON call_transcripts (org_id, call_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_call_transcripts_org_created_at
        ON call_transcripts (org_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_technician_schedules_org_tech
        ON technician_schedules (org_id, technician_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_organizations_slug
        ON organizations (slug)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_organizations_slug")
    op.execute("DROP INDEX IF EXISTS idx_technician_schedules_org_tech")
    op.execute("DROP INDEX IF EXISTS idx_call_transcripts_org_created_at")
    op.execute("DROP INDEX IF EXISTS idx_call_transcripts_org_call_id")
    op.execute("DROP INDEX IF EXISTS idx_dispatch_jobs_scheduled_window_start")
    op.execute("DROP INDEX IF EXISTS idx_dispatch_jobs_org_customer")
    op.execute("DROP INDEX IF EXISTS idx_dispatch_jobs_org_status")
    op.execute("DROP INDEX IF EXISTS idx_customers_org_churn_risk")
    op.execute("DROP INDEX IF EXISTS idx_customers_org_phone")
