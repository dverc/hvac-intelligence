from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrgSettings(Base):
    __tablename__ = "org_settings"
    __table_args__ = (UniqueConstraint("org_id", name="uq_org_settings_org_id"),)

    setting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    phone_display: Mapped[Optional[str]] = mapped_column(String(20))
    address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(2))
    zip: Mapped[Optional[str]] = mapped_column(String(20))
    agent_greeting: Mapped[Optional[str]] = mapped_column(Text)
    agent_name: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="AI Assistant"
    )
    business_hours_start: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="8"
    )
    business_hours_end: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="18"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="America/Los_Angeles"
    )
    vapi_assistant_id: Mapped[Optional[str]] = mapped_column(String(255))
    vapi_phone_number_id: Mapped[Optional[str]] = mapped_column(String(128))
    vapi_phone_number: Mapped[Optional[str]] = mapped_column(String(50))
    outbound_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    outbound_disclosure_style: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="FRIENDLY"
    )
    max_outbound_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="2"
    )
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    onboarding_step: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
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
