from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChurnScore(Base):
    __tablename__ = "churn_scores"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('CUSTOMER', 'EMPLOYEE')",
            name="ck_churn_scores_entity_type",
        ),
        CheckConstraint(
            "risk_tier IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_churn_scores_risk_tier",
        ),
        Index(
            "idx_churn_entity",
            "entity_type",
            "entity_id",
            "score_timestamp",
            postgresql_ops={"score_timestamp": "DESC"},
        ),
        Index(
            "idx_churn_tier",
            "risk_tier",
            "score_timestamp",
            postgresql_ops={"score_timestamp": "DESC"},
        ),
    )

    score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_type: Mapped[str] = mapped_column(String(8), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    score_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    churn_probability: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(10), nullable=False)
    feature_contributions: Mapped[Optional[list]] = mapped_column(JSONB)
    model_version: Mapped[Optional[str]] = mapped_column(String(20))
    scoring_trigger: Mapped[Optional[str]] = mapped_column(String(30))
    prediction_horizon_days: Mapped[int] = mapped_column(Integer, server_default="90")
    intervention_applied: Mapped[bool] = mapped_column(Boolean, server_default="false")
    intervention_type: Mapped[Optional[str]] = mapped_column(String(50))
    post_intervention_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    score_delta: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 3),
        Computed(
            "COALESCE(post_intervention_score, churn_probability) - churn_probability",
            persisted=True,
        ),
    )
