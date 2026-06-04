"""GIN index on organizations.settings for Drive folder lookups

Revision ID: 014_org_drive_folder
Revises: 013_dispatch_external_job_id
Create Date: 2026-06-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "014_org_drive_folder"
down_revision: Union[str, None] = "013_dispatch_external_job_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_organizations_settings_gin
        ON organizations USING gin(settings)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_organizations_settings_gin")
