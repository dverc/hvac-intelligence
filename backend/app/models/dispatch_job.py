from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SEED_ORG_ID_STR
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.call_transcript import CallTranscript
    from app.models.customer import Customer
    from app.models.equipment import Equipment
    from app.models.technician import Technician


class DispatchJob(Base):
    __tablename__ = "dispatch_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_status IN ('SCHEDULED','IN_PROGRESS','COMPLETED','CANCELLED','RESCHEDULED')",
            name="ck_dispatch_jobs_job_status",
        ),
        CheckConstraint(
            "priority IN ('P1','P2','P3','P4')",
            name="ck_dispatch_jobs_priority",
        ),
        CheckConstraint(
            "customer_rating IS NULL OR (customer_rating >= 1 AND customer_rating <= 5)",
            name="ck_dispatch_jobs_customer_rating",
        ),
        Index("idx_jobs_customer", "customer_id"),
        Index("idx_jobs_tech", "technician_id", "scheduled_window_start"),
        Index("idx_jobs_status", "job_status"),
        UniqueConstraint("org_id", "job_number", name="uq_dispatch_jobs_org_job_number"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        server_default=text(f"'{SEED_ORG_ID_STR}'"),
    )
    job_number: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False
    )
    equipment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipment.equipment_id")
    )
    technician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("technicians.technician_id")
    )
    call_transcript_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "call_transcripts.transcript_id",
            use_alter=True,
            name="fk_dispatch_jobs_call_transcript_id",
        ),
    )
    job_status: Mapped[str] = mapped_column(String(20), server_default="SCHEDULED")
    priority: Mapped[str] = mapped_column(String(2), server_default="P3")
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    issue_description: Mapped[Optional[str]] = mapped_column(Text)
    scheduled_window_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    scheduled_window_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    actual_arrival: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actual_completion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    parts_used: Mapped[list] = mapped_column(JSONB, server_default="[]")
    labor_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    invoice_amount_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    customer_rating: Mapped[Optional[int]] = mapped_column(SmallInteger)
    customer_feedback: Mapped[Optional[str]] = mapped_column(Text)
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

    customer: Mapped[Customer] = relationship(back_populates="dispatch_jobs")
    equipment: Mapped[Optional[Equipment]] = relationship(back_populates="dispatch_jobs")
    technician: Mapped[Optional[Technician]] = relationship(back_populates="dispatch_jobs")
    linked_transcript: Mapped[Optional[CallTranscript]] = relationship(
        foreign_keys=[call_transcript_id],
    )
