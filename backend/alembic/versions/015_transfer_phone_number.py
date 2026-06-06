"""add transfer_phone_number to organizations

Revision ID: 015_transfer_phone_number
Revises: 014_org_drive_folder
Create Date: 2026-06-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_transfer_phone_number"
down_revision: Union[str, None] = "014_org_drive_folder"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("transfer_phone_number", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "transfer_phone_number")
