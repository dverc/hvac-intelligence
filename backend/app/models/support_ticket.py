from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SEED_ORG_ID_STR
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.call_transcript import CallTranscript
    from app.models.customer import Customer


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        CheckConstraint(
            "ticket_type IN ("
            "'BILLING_DISPUTE','WARRANTY_CLAIM','COMPLAINT_ESCALATION',"
            "'SAFETY_CONCERN','REFUND_REQUEST','MANAGER_CALLBACK','UNRESOLVED_TECHNICAL'"
            ")",
            name="ck_support_tickets_ticket_type",
        ),
        CheckConstraint(
            "priority IN ('P1','P2','P3')",
            name="ck_support_tickets_priority",
        ),
        CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','RESOLVED','CLOSED')",
            name="ck_support_tickets_status",
        ),
        Index("idx_support_tickets_customer", "customer_id"),
        Index("idx_support_tickets_status", "status"),
        Index("idx_support_tickets_priority", "priority"),
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        server_default=text(f"'{SEED_ORG_ID_STR}'"),
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False
    )
    call_transcript_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_transcripts.transcript_id")
    )
    ticket_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="OPEN")
    preferred_callback_time: Mapped[Optional[str]] = mapped_column(String(255))
    created_by: Mapped[str] = mapped_column(String(20), server_default="VOICE_AGENT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship(back_populates="support_tickets")
    call_transcript: Mapped[Optional[CallTranscript]] = relationship(
        back_populates="support_tickets"
    )
