"""add org_id to all tenant tables (safe backfill)

Revision ID: 006_add_org_id
Revises: 005_organizations
Create Date: 2026-06-02

Adds a NOT NULL org_id FK to every tenant-scoped table using a safe,
zero-invalid-window pattern per table:
  1. add nullable org_id
  2. backfill existing rows to SEED_ORG_ID
  3. set NOT NULL + server_default = SEED_ORG_ID
  4. add FK -> organizations(org_id) ON DELETE RESTRICT
  5. add index on org_id

The server_default is intentionally retained for deploy safety so any
in-flight INSERT during rollout still produces a valid (seed) tenant row.
A later phase may drop the server_default once all writers set org_id.

Global UNIQUE constraints that must be tenant-scoped (phone/external_id/
employee_number/serial_number/job_number) are dropped and replaced with
composite (org_id, <key>) constraints. call_transcripts.call_id stays
globally unique because it is a Vapi-generated UUID.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.constants import SEED_ORG_ID_STR

revision: str = "006_add_org_id"
down_revision: Union[str, None] = "005_organizations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every tenant-scoped table.
_TENANT_TABLES: tuple[str, ...] = (
    "customers",
    "equipment",
    "call_transcripts",
    "dispatch_jobs",
    "technicians",
    "churn_scores",
    "feature_store",
    "support_tickets",
)


def _add_org_id(table: str) -> None:
    op.add_column(table, sa.Column("org_id", sa.UUID(), nullable=True))
    op.execute(
        sa.text(
            f"UPDATE {table} SET org_id = :seed WHERE org_id IS NULL"
        ).bindparams(seed=SEED_ORG_ID_STR)
    )
    op.alter_column(
        table,
        "org_id",
        existing_type=sa.UUID(),
        nullable=False,
        server_default=sa.text(f"'{SEED_ORG_ID_STR}'"),
    )
    op.create_foreign_key(
        f"fk_{table}_org_id",
        table,
        "organizations",
        ["org_id"],
        ["org_id"],
        ondelete="RESTRICT",
    )
    op.create_index(f"ix_{table}_org_id", table, ["org_id"])


def _drop_org_id(table: str) -> None:
    op.drop_index(f"ix_{table}_org_id", table_name=table)
    op.drop_constraint(f"fk_{table}_org_id", table, type_="foreignkey")
    op.drop_column(table, "org_id")


def upgrade() -> None:
    for table in _TENANT_TABLES:
        _add_org_id(table)

    # ── Tenant-scoped uniqueness (replace global UNIQUE with composite) ──
    op.drop_constraint("customers_external_id_key", "customers", type_="unique")
    op.create_unique_constraint(
        "uq_customers_org_external_id", "customers", ["org_id", "external_id"]
    )
    op.create_index(
        "idx_customers_org_phone", "customers", ["org_id", "phone_primary"]
    )

    op.drop_constraint(
        "technicians_employee_number_key", "technicians", type_="unique"
    )
    op.create_unique_constraint(
        "uq_technicians_org_employee_number",
        "technicians",
        ["org_id", "employee_number"],
    )

    op.drop_constraint("equipment_serial_number_key", "equipment", type_="unique")
    op.create_unique_constraint(
        "uq_equipment_org_serial_number", "equipment", ["org_id", "serial_number"]
    )

    op.drop_constraint(
        "dispatch_jobs_job_number_key", "dispatch_jobs", type_="unique"
    )
    op.create_unique_constraint(
        "uq_dispatch_jobs_org_job_number",
        "dispatch_jobs",
        ["org_id", "job_number"],
    )

    op.drop_constraint(
        "uq_feature_store_entity_window", "feature_store", type_="unique"
    )
    op.create_unique_constraint(
        "uq_feature_store_org_entity_window",
        "feature_store",
        ["org_id", "entity_type", "entity_id", "window_end", "window_days"],
    )


def downgrade() -> None:
    # ── Restore global uniqueness ──
    op.drop_constraint(
        "uq_feature_store_org_entity_window", "feature_store", type_="unique"
    )
    op.create_unique_constraint(
        "uq_feature_store_entity_window",
        "feature_store",
        ["entity_type", "entity_id", "window_end", "window_days"],
    )

    op.drop_constraint(
        "uq_dispatch_jobs_org_job_number", "dispatch_jobs", type_="unique"
    )
    op.create_unique_constraint(
        "dispatch_jobs_job_number_key", "dispatch_jobs", ["job_number"]
    )

    op.drop_constraint(
        "uq_equipment_org_serial_number", "equipment", type_="unique"
    )
    op.create_unique_constraint(
        "equipment_serial_number_key", "equipment", ["serial_number"]
    )

    op.drop_constraint(
        "uq_technicians_org_employee_number", "technicians", type_="unique"
    )
    op.create_unique_constraint(
        "technicians_employee_number_key", "technicians", ["employee_number"]
    )

    op.drop_index("idx_customers_org_phone", table_name="customers")
    op.drop_constraint(
        "uq_customers_org_external_id", "customers", type_="unique"
    )
    op.create_unique_constraint(
        "customers_external_id_key", "customers", ["external_id"]
    )

    # ── Drop org_id from every table (reverse order) ──
    for table in reversed(_TENANT_TABLES):
        _drop_org_id(table)
