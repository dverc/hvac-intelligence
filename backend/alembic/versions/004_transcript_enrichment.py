"""transcript enrichment columns

Revision ID: 004_transcript_enrichment
Revises: 003_support_tickets
Create Date: 2026-06-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_transcript_enrichment"
down_revision: Union[str, None] = "003_support_tickets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "call_transcripts",
        sa.Column("recording_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "call_transcripts",
        sa.Column("call_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "call_transcripts",
        sa.Column("vapi_end_reason", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "call_transcripts",
        sa.Column("call_cost_usd", sa.Numeric(precision=10, scale=4), nullable=True),
    )
    op.add_column(
        "call_transcripts",
        sa.Column("vapi_assistant_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("call_transcripts", "vapi_assistant_id")
    op.drop_column("call_transcripts", "call_cost_usd")
    op.drop_column("call_transcripts", "vapi_end_reason")
    op.drop_column("call_transcripts", "call_summary")
    op.drop_column("call_transcripts", "recording_url")
