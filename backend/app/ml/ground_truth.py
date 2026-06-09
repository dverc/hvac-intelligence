"""Ground-truth churn outcome tracking for model evaluation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.churn_model import default_rule_score, predict_probability
from app.ml.feature_engineering import build_customer_features
from app.ml.model_registry import load_model
from app.models.customer import Customer
from app.models.ground_truth_label import GroundTruthLabel


async def record_churn_event(
    customer_id: uuid.UUID | str,
    churned: bool,
    db: AsyncSession,
    *,
    notes: str | None = None,
) -> GroundTruthLabel:
    """Persist a labeled churn outcome with feature snapshot and model score."""
    cid = uuid.UUID(str(customer_id))
    customer = await db.get(Customer, cid)
    if customer is None:
        raise ValueError(f"Customer {customer_id} not found")

    features = await build_customer_features(cid, db)
    model = load_model()
    if model is not None:
        probability = predict_probability(features, model)
    else:
        probability = default_rule_score(features)

    label = GroundTruthLabel(
        customer_id=cid,
        org_id=customer.org_id,
        churned=churned,
        recorded_at=datetime.now(timezone.utc),
        feature_snapshot=features,
        churn_probability_at_time=Decimal(str(round(probability, 3))),
        notes=notes,
    )
    db.add(label)
    await db.flush()
    return label
