"""support_tickets table

Revision ID: 003_support_tickets
Revises: 002_computed_views
Create Date: 2026-05-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_support_tickets"
down_revision: Union[str, None] = "002_computed_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("call_transcript_id", sa.UUID(), nullable=True),
        sa.Column("ticket_type", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="OPEN", nullable=False),
        sa.Column("preferred_callback_time", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=20), server_default="VOICE_AGENT", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "ticket_type IN ("
            "'BILLING_DISPUTE','WARRANTY_CLAIM','COMPLAINT_ESCALATION',"
            "'SAFETY_CONCERN','REFUND_REQUEST','MANAGER_CALLBACK','UNRESOLVED_TECHNICAL'"
            ")",
            name="ck_support_tickets_ticket_type",
        ),
        sa.CheckConstraint(
            "priority IN ('P1','P2','P3')",
            name="ck_support_tickets_priority",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','RESOLVED','CLOSED')",
            name="ck_support_tickets_status",
        ),
        sa.ForeignKeyConstraint(["call_transcript_id"], ["call_transcripts.transcript_id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.customer_id"]),
        sa.PrimaryKeyConstraint("ticket_id"),
    )
    op.create_index("idx_support_tickets_customer", "support_tickets", ["customer_id"])
    op.create_index("idx_support_tickets_status", "support_tickets", ["status"])
    op.create_index("idx_support_tickets_priority", "support_tickets", ["priority"])


def downgrade() -> None:
    op.drop_index("idx_support_tickets_priority", table_name="support_tickets")
    op.drop_index("idx_support_tickets_status", table_name="support_tickets")
    op.drop_index("idx_support_tickets_customer", table_name="support_tickets")
    op.drop_table("support_tickets")
