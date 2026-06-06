from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Organization(Base):
    """A tenant. Every tenant-scoped row references one organization."""

    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "industry IN ('hvac','plumbing','electrical','isp',"
            "'appliance_repair','locksmith','pest_control','other')",
            name="ck_organizations_industry",
        ),
        CheckConstraint(
            "plan_tier IN ('starter','professional','enterprise')",
            name="ck_organizations_plan_tier",
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    industry: Mapped[str] = mapped_column(String(50), nullable=False)
    business_phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    vapi_assistant_id: Mapped[str | None] = mapped_column(String(128))
    vapi_phone_number_id: Mapped[str | None] = mapped_column(String(128))
    plan_tier: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="starter"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    transfer_phone_number: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
