"""add skills array to technicians

Revision ID: 016_technician_skills
Revises: 015_transfer_phone_number
Create Date: 2026-06-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016_technician_skills"
down_revision: Union[str, None] = "015_transfer_phone_number"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "technicians",
        sa.Column(
            "skills",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("technicians", "skills")
