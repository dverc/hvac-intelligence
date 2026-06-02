from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ServiceCatalog(Base):
    """Tenant-scoped service catalog for exact pricing and duration lookups."""

    __tablename__ = "service_catalog"
    __table_args__ = (
        UniqueConstraint("org_id", "service_code", name="uq_service_catalog_org_code"),
        Index("idx_service_catalog_org_category", "org_id", "category"),
        Index("idx_service_catalog_org_active", "org_id", "is_active"),
    )

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_code: Mapped[str] = mapped_column(String(100), nullable=False)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    base_price_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    price_max_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    price_notes: Mapped[Optional[str]] = mapped_column(String(500))
    duration_minutes_min: Mapped[Optional[int]] = mapped_column(Integer)
    duration_minutes_max: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    requires_equipment_type: Mapped[Optional[str]] = mapped_column(String(100))
    emergency_surcharge_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
