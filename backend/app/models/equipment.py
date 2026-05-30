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
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.dispatch_job import DispatchJob


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint(
            "equipment_type IN ('AC_UNIT','FURNACE','HEAT_PUMP','AIR_HANDLER','MINI_SPLIT','OTHER')",
            name="ck_equipment_equipment_type",
        ),
    )

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
    )
    make: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    equipment_type: Mapped[Optional[str]] = mapped_column(String(50))
    install_date: Mapped[Optional[date]] = mapped_column(Date)
    warranty_expiry: Mapped[Optional[date]] = mapped_column(Date)
    last_service_date: Mapped[Optional[date]] = mapped_column(Date)
    service_count: Mapped[int] = mapped_column(Integer, server_default="0")
    # Spec §3.1.2 defines GENERATED ALWAYS AS (EXTRACT(YEAR FROM AGE(NOW(), install_date))).
    # PostgreSQL requires immutable generated expressions; NOW() is not allowed.
    age_years: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    efficiency_rating: Mapped[Optional[str]] = mapped_column(String(20))
    known_issues: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    manual_url: Mapped[Optional[str]] = mapped_column(String(500))
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

    customer: Mapped[Customer] = relationship(back_populates="equipment")
    dispatch_jobs: Mapped[list[DispatchJob]] = relationship(back_populates="equipment")
