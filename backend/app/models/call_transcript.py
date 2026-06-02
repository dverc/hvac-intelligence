from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SEED_ORG_ID_STR
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.dispatch_job import DispatchJob
    from app.models.support_ticket import SupportTicket
    from app.models.technician import Technician


class CallTranscript(Base):
    __tablename__ = "call_transcripts"
    __table_args__ = (
        CheckConstraint(
            "call_direction IN ('INBOUND', 'OUTBOUND')",
            name="ck_call_transcripts_call_direction",
        ),
        CheckConstraint(
            "call_outcome IN ('DISPATCHED','FAQ_RESOLVED','ESCALATED_HUMAN','ABANDONED','RETAINED','VOICEMAIL')",
            name="ck_call_transcripts_call_outcome",
        ),
        CheckConstraint(
            "sentiment_overall IS NULL OR (sentiment_overall >= -1 AND sentiment_overall <= 1)",
            name="ck_call_transcripts_sentiment_overall",
        ),
        Index("idx_transcripts_customer", "customer_id"),
        Index("idx_transcripts_outcome", "call_outcome"),
        Index(
            "idx_transcripts_start",
            "call_start_utc",
            postgresql_ops={"call_start_utc": "DESC"},
        ),
        Index(
            "idx_transcripts_intervention",
            "intervention_successful",
            postgresql_where=text("intervention_successful = TRUE"),
        ),
    )

    transcript_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        server_default=text(f"'{SEED_ORG_ID_STR}'"),
    )
    # call_id is a Vapi-generated UUID — globally unique by construction, so the
    # unique constraint remains global (not tenant-scoped) by design.
    call_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id")
    )
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("technicians.technician_id")
    )
    dispatch_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "dispatch_jobs.job_id",
            use_alter=True,
            name="fk_call_transcripts_dispatch_job_id",
        ),
    )
    call_direction: Mapped[str] = mapped_column(String(8), server_default="INBOUND")
    call_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    call_end_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    call_outcome: Mapped[Optional[str]] = mapped_column(String(50))
    recording_url: Mapped[Optional[str]] = mapped_column(String(500))
    call_summary: Mapped[Optional[str]] = mapped_column(Text)
    vapi_end_reason: Mapped[Optional[str]] = mapped_column(String(100))
    call_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    vapi_assistant_id: Mapped[Optional[str]] = mapped_column(String(128))
    transcript_raw: Mapped[Optional[str]] = mapped_column(Text)
    transcript_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    sentiment_overall: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    sentiment_trajectory: Mapped[Optional[list]] = mapped_column(JSONB)
    dominant_intent: Mapped[Optional[str]] = mapped_column(String(50))
    intent_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    entities_extracted: Mapped[Optional[dict]] = mapped_column(JSONB)
    escalation_detected: Mapped[bool] = mapped_column(Boolean, server_default="false")
    hesitation_markers: Mapped[Optional[dict]] = mapped_column(JSONB)
    emotion_labels: Mapped[Optional[dict]] = mapped_column(JSONB)
    churn_risk_at_call_start: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    churn_risk_at_call_end: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    intervention_successful: Mapped[Optional[bool]] = mapped_column(Boolean)
    rag_queries_issued: Mapped[int] = mapped_column(Integer, server_default="0")
    rag_chunks_used: Mapped[Optional[list]] = mapped_column(JSONB)
    tool_calls_log: Mapped[Optional[list]] = mapped_column(JSONB)
    vapi_metadata: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    customer: Mapped[Optional[Customer]] = relationship(back_populates="transcripts")
    technician: Mapped[Optional[Technician]] = relationship(
        back_populates="call_transcripts"
    )
    dispatch_job: Mapped[Optional[DispatchJob]] = relationship(
        foreign_keys=[dispatch_job_id],
    )
    support_tickets: Mapped[list[SupportTicket]] = relationship(
        back_populates="call_transcript"
    )
