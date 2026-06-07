"""add customer_tier to customers

Revision ID: 022_customer_tier
Revises: 021_dispatch_reminder_fields
Create Date: 2026-06-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_customer_tier"
down_revision: Union[str, None] = "021_dispatch_reminder_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column(
            "customer_tier",
            sa.String(length=20),
            nullable=False,
            server_default="standard",
        ),
    )
    op.create_check_constraint(
        "ck_customers_customer_tier",
        "customers",
        "customer_tier IN ('standard','preferred','vip')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_customers_customer_tier", "customers", type_="check")
    op.drop_column("customers", "customer_tier")
