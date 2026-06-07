"""add external_id to technicians for Jobber sync

Revision ID: 020_technician_external_id
Revises: 019_org_vapi_config
Create Date: 2026-06-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_technician_external_id"
down_revision: Union[str, None] = "019_org_vapi_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "technicians",
        sa.Column("external_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("technicians", "external_id")
