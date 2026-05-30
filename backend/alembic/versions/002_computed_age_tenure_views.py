"""computed age_years and tenure_years read views

Revision ID: 002_computed_views
Revises: b2618c74dc5a
Create Date: 2026-05-29

Option C (Phase 1 decision): PostgreSQL views compute age/tenure at read time using AGE(NOW(), ...).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002_computed_views"
down_revision: Union[str, None] = "b2618c74dc5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW v_equipment_computed AS
        SELECT
            e.*,
            CASE
                WHEN e.install_date IS NOT NULL THEN
                    EXTRACT(YEAR FROM AGE(NOW(), e.install_date))::NUMERIC(5, 2)
                ELSE NULL
            END AS age_years_computed
        FROM equipment e;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW v_technicians_computed AS
        SELECT
            t.*,
            EXTRACT(YEAR FROM AGE(NOW(), t.hire_date))::NUMERIC(5, 2) AS tenure_years_computed
        FROM technicians t;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_technicians_computed")
    op.execute("DROP VIEW IF EXISTS v_equipment_computed")
