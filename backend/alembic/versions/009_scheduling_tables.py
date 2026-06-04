"""scheduling tables + default working hours seed

Revision ID: 009_scheduling_tables
Revises: 008_document_registry
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.constants import SEED_ORG_ID_STR

revision: str = "009_scheduling_tables"
down_revision: Union[str, None] = "008_document_registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "technician_schedules",
        sa.Column("schedule_id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("technician_id", sa.UUID(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "effective_from",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.org_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["technician_id"], ["technicians.technician_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("schedule_id"),
        sa.UniqueConstraint(
            "org_id",
            "technician_id",
            "day_of_week",
            name="uq_technician_schedules_org_tech_dow",
        ),
    )
    op.create_index(
        "idx_technician_schedules_org_tech_dow",
        "technician_schedules",
        ["org_id", "technician_id", "day_of_week"],
    )
    op.create_index(
        op.f("ix_technician_schedules_org_id"),
        "technician_schedules",
        ["org_id"],
        unique=False,
    )

    op.create_table(
        "schedule_overrides",
        sa.Column("override_id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("technician_id", sa.UUID(), nullable=False),
        sa.Column("override_date", sa.Date(), nullable=False),
        sa.Column("override_type", sa.String(length=50), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "override_type IN ('day_off','custom_hours','emergency_only')",
            name="ck_schedule_overrides_type",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.org_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["technician_id"], ["technicians.technician_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("override_id"),
        sa.UniqueConstraint(
            "org_id",
            "technician_id",
            "override_date",
            name="uq_schedule_overrides_org_tech_date",
        ),
    )
    op.create_index(
        op.f("ix_schedule_overrides_org_id"),
        "schedule_overrides",
        ["org_id"],
        unique=False,
    )

    # Seed Mon–Fri 08:00–17:00 for all seed-org technicians.
    op.execute(
        sa.text(
            """
            INSERT INTO technician_schedules
                (schedule_id, org_id, technician_id, day_of_week,
                 start_time, end_time, is_active, effective_from)
            SELECT
                gen_random_uuid(),
                t.org_id,
                t.technician_id,
                dow,
                TIME '08:00',
                TIME '17:00',
                true,
                CURRENT_DATE
            FROM technicians t
            CROSS JOIN generate_series(0, 4) AS dow
            WHERE t.org_id = CAST(:org_id AS UUID)
            ON CONFLICT (org_id, technician_id, day_of_week) DO NOTHING
            """
        ).bindparams(org_id=SEED_ORG_ID_STR)
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_schedule_overrides_org_id"), table_name="schedule_overrides")
    op.drop_table("schedule_overrides")
    op.drop_index(
        op.f("ix_technician_schedules_org_id"), table_name="technician_schedules"
    )
    op.drop_index(
        "idx_technician_schedules_org_tech_dow", table_name="technician_schedules"
    )
    op.drop_table("technician_schedules")
