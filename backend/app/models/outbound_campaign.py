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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.organization import Organization


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    __table_args__ = (
        Index("idx_consent_records_customer_type", "customer_id", "consent_type", "revoked_at"),
    )

    consent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    consent_type: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_method: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_call_id: Mapped[Optional[str]] = mapped_column(String(128))
    consent_text: Mapped[str] = mapped_column(Text, nullable=False)
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revocation_method: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    customer: Mapped["Customer"] = relationship(foreign_keys=[customer_id])


class OutboundCampaign(Base):
    __tablename__ = "outbound_campaigns"
    __table_args__ = (
        CheckConstraint(
            "campaign_type IN ('REACTIVATION','RETENTION','REMINDER')",
            name="ck_outbound_campaigns_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','PAUSED','COMPLETED','RUNNING')",
            name="ck_outbound_campaigns_status",
        ),
        CheckConstraint(
            "disclosure_style IN ('FRIENDLY','FORMAL')",
            name="ck_outbound_campaigns_disclosure_style",
        ),
        Index("idx_outbound_campaigns_org_status", "org_id", "status"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="DRAFT")
    churn_score_threshold: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, server_default="0.750"
    )
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    calling_hours_start: Mapped[int] = mapped_column(Integer, nullable=False, server_default="9")
    calling_hours_end: Mapped[int] = mapped_column(Integer, nullable=False, server_default="18")
    disclosure_style: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="FRIENDLY"
    )
    total_customers_targeted: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    total_calls_made: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_consented: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_booked: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    organization: Mapped["Organization"] = relationship(foreign_keys=[org_id])
    attempts: Mapped[list["OutboundCallAttempt"]] = relationship(back_populates="campaign")


class OutboundCallAttempt(Base):
    __tablename__ = "outbound_call_attempts"
    __table_args__ = (
        Index("idx_outbound_attempts_campaign", "campaign_id", "status"),
        Index("idx_outbound_attempts_customer_created", "customer_id", "created_at"),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outbound_campaigns.campaign_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="PENDING")
    vapi_call_id: Mapped[Optional[str]] = mapped_column(String(128))
    attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    outcome: Mapped[Optional[str]] = mapped_column(String(32))
    disclosure_delivered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    campaign: Mapped["OutboundCampaign"] = relationship(back_populates="attempts")
    customer: Mapped["Customer"] = relationship(foreign_keys=[customer_id])
