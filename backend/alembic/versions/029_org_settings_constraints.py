"""org_settings onboarding_step range and outbound RUNNING status

Revision ID: 029_org_settings_constraints
Revises: 028_org_settings
Create Date: 2026-06-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "029_org_settings_constraints"
down_revision: Union[str, None] = "028_org_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_onboarding_step_range",
        "org_settings",
        "onboarding_step >= 0 AND onboarding_step <= 5",
    )
    op.execute(
        "ALTER TABLE outbound_campaigns "
        "DROP CONSTRAINT IF EXISTS ck_outbound_campaigns_status"
    )
    op.create_check_constraint(
        "ck_outbound_campaigns_status",
        "outbound_campaigns",
        "status IN ('DRAFT','ACTIVE','PAUSED','COMPLETED','RUNNING')",
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE outbound_campaigns "
        "DROP CONSTRAINT IF EXISTS ck_outbound_campaigns_status"
    )
    op.create_check_constraint(
        "ck_outbound_campaigns_status",
        "outbound_campaigns",
        "status IN ('DRAFT','ACTIVE','PAUSED','COMPLETED')",
    )
    op.drop_constraint("ck_onboarding_step_range", "org_settings", type_="check")
