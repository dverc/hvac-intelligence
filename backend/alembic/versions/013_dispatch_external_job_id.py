"""add external_job_id to dispatch_jobs

Revision ID: 013_dispatch_external_job_id
Revises: 012_jobber_tokens
Create Date: 2026-06-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_dispatch_external_job_id"
down_revision: Union[str, None] = "012_jobber_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dispatch_jobs",
        sa.Column("external_job_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_dispatch_jobs_org_external_job_id",
        "dispatch_jobs",
        ["org_id", "external_job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_dispatch_jobs_org_external_job_id", table_name="dispatch_jobs")
    op.drop_column("dispatch_jobs", "external_job_id")
