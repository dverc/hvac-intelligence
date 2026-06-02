from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import SEED_ORG_ID_STR
from app.core.database import Base


class FeatureStore(Base):
    __tablename__ = "feature_store"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('CUSTOMER', 'EMPLOYEE')",
            name="ck_feature_store_entity_type",
        ),
        UniqueConstraint(
            "org_id",
            "entity_type",
            "entity_id",
            "window_end",
            "window_days",
            name="uq_feature_store_org_entity_window",
        ),
        Index(
            "idx_features_entity",
            "entity_type",
            "entity_id",
            "computed_at",
            postgresql_ops={"computed_at": "DESC"},
        ),
    )

    feature_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        server_default=text(f"'{SEED_ORG_ID_STR}'"),
    )
    entity_type: Mapped[str] = mapped_column(String(8), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="90")

    total_calls_window: Mapped[int] = mapped_column(Integer, server_default="0")
    inbound_call_count: Mapped[int] = mapped_column(Integer, server_default="0")
    outbound_call_count: Mapped[int] = mapped_column(Integer, server_default="0")
    avg_call_duration_seconds: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    escalation_frequency: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    escalation_count: Mapped[int] = mapped_column(Integer, server_default="0")
    sentiment_first_call: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    sentiment_last_call: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    sentiment_degradation_slope: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    sentiment_std_dev: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    avg_sentiment_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    min_sentiment_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    negative_call_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    hesitation_marker_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    filler_word_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    anger_emotion_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    complaint_mention_count: Mapped[int] = mapped_column(Integer, server_default="0")
    recurrence_complaint_count: Mapped[int] = mapped_column(Integer, server_default="0")

    avg_time_to_resolution_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    time_to_resolution_std_dev: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    max_time_to_resolution_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    dispatch_cancellation_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    rescheduling_count: Mapped[int] = mapped_column(Integer, server_default="0")
    open_ticket_age_days_avg: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    open_ticket_count: Mapped[int] = mapped_column(Integer, server_default="0")
    p1_p2_job_count: Mapped[int] = mapped_column(Integer, server_default="0")
    same_issue_recurrence_count: Mapped[int] = mapped_column(Integer, server_default="0")
    technician_change_count: Mapped[int] = mapped_column(Integer, server_default="0")

    payment_delay_days_avg: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    payment_failure_count: Mapped[int] = mapped_column(Integer, server_default="0")
    days_since_last_positive_call: Mapped[Optional[int]] = mapped_column(Integer)
    days_since_last_service: Mapped[Optional[int]] = mapped_column(Integer)
    contract_days_until_renewal: Mapped[Optional[int]] = mapped_column(Integer)
    customer_rating_avg_90d: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    equipment_age_years: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    warranty_expired: Mapped[bool] = mapped_column(Boolean, server_default="false")

    complaint_rate_90d: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    avg_customer_rating_90d: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    schedule_conflict_count: Mapped[int] = mapped_column(Integer, server_default="0")
    overtime_hours_90d: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    internal_escalation_count: Mapped[int] = mapped_column(Integer, server_default="0")

    feature_vector: Mapped[Optional[list]] = mapped_column(Vector(64))
