from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.call_transcript import CallTranscript
    from app.models.churn_score import ChurnScore
    from app.models.dispatch_job import DispatchJob
    from app.models.equipment import Equipment
    from app.models.support_ticket import SupportTicket
    from app.models.technician import Technician


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(
            "account_status IN ('ACTIVE','SUSPENDED','CHURNED','PROSPECT')",
            name="ck_customers_account_status",
        ),
        CheckConstraint(
            "contract_type IN ('ANNUAL_MAINTENANCE','RESIDENTIAL_OTC','COMMERCIAL_SLA')",
            name="ck_customers_contract_type",
        ),
        Index("idx_customers_phone", "phone_primary"),
        Index("idx_customers_status", "account_status"),
        Index(
            "idx_customers_churn_risk",
            text("(metadata->>'churn_tier')"),
        ),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    external_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_primary: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_secondary: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    address_line2: Mapped[Optional[str]] = mapped_column(String(100))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(2))
    zip: Mapped[Optional[str]] = mapped_column(String(10))
    account_status: Mapped[str] = mapped_column(String(20), server_default="ACTIVE")
    customer_since: Mapped[date] = mapped_column(Date, nullable=False)
    contract_type: Mapped[Optional[str]] = mapped_column(String(30))
    contract_value_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    payment_method: Mapped[Optional[str]] = mapped_column(String(30))
    preferred_tech_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("technicians.technician_id")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    preferred_tech: Mapped[Optional[Technician]] = relationship(
        back_populates="preferred_by_customers",
        foreign_keys=[preferred_tech_id],
    )
    equipment: Mapped[list[Equipment]] = relationship(back_populates="customer")
    transcripts: Mapped[list[CallTranscript]] = relationship(back_populates="customer")
    dispatch_jobs: Mapped[list[DispatchJob]] = relationship(back_populates="customer")
    churn_scores: Mapped[list[ChurnScore]] = relationship(
        primaryjoin="and_(ChurnScore.entity_id==Customer.customer_id, ChurnScore.entity_type=='CUSTOMER')",
        foreign_keys="ChurnScore.entity_id",
        viewonly=True,
    )
    support_tickets: Mapped[list[SupportTicket]] = relationship(back_populates="customer")
