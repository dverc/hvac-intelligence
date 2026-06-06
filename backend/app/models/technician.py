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
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SEED_ORG_ID_STR
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.call_transcript import CallTranscript
    from app.models.customer import Customer
    from app.models.dispatch_job import DispatchJob


class Technician(Base):
    __tablename__ = "technicians"
    __table_args__ = (
        CheckConstraint(
            "employment_status IN ('ACTIVE','ON_LEAVE','TERMINATED','PROBATION')",
            name="ck_technicians_employment_status",
        ),
        CheckConstraint(
            "churn_risk_tier IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_technicians_churn_risk_tier",
        ),
        UniqueConstraint(
            "org_id", "employee_number", name="uq_technicians_org_employee_number"
        ),
    )

    technician_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        server_default=text(f"'{SEED_ORG_ID_STR}'"),
    )
    employee_number: Mapped[str] = mapped_column(String(32), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    employment_status: Mapped[str] = mapped_column(String(20), server_default="ACTIVE")
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Spec §3.1.4 defines GENERATED ALWAYS AS (EXTRACT(YEAR FROM AGE(NOW(), hire_date))).
    # PostgreSQL requires immutable generated expressions; NOW() is not allowed.
    tenure_years: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    certifications: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'")
    )
    service_zones: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(20)))
    avg_customer_rating: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    jobs_completed_90d: Mapped[int] = mapped_column(Integer, server_default="0")
    complaints_received_90d: Mapped[int] = mapped_column(Integer, server_default="0")
    scheduled_jobs: Mapped[list] = mapped_column(JSONB, server_default="[]")
    churn_risk_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), server_default="0.0"
    )
    churn_risk_tier: Mapped[str] = mapped_column(String(10), server_default="LOW")
    hr_flags: Mapped[list] = mapped_column(JSONB, server_default="[]")
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

    preferred_by_customers: Mapped[list[Customer]] = relationship(
        back_populates="preferred_tech",
        foreign_keys="Customer.preferred_tech_id",
    )
    call_transcripts: Mapped[list[CallTranscript]] = relationship(
        back_populates="technician"
    )
    dispatch_jobs: Mapped[list[DispatchJob]] = relationship(back_populates="technician")
