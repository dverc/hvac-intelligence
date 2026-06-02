from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.churn_score import ChurnScore
from app.models.customer import Customer


TIER_DEFAULT_PROBABILITY = {
    "LOW": 0.18,
    "MEDIUM": 0.48,
    "HIGH": 0.71,
    "CRITICAL": 0.91,
}

INTERVENTIONS_BY_TIER = {
    "LOW": [],
    "MEDIUM": ["LOYALTY_DISCOUNT_OFFER"],
    "HIGH": ["PRIORITY_DISPATCH", "LOYALTY_DISCOUNT_OFFER", "MANAGER_CALLBACK"],
    "CRITICAL": [
        "PRIORITY_DISPATCH",
        "LOYALTY_DISCOUNT_OFFER",
        "MANAGER_CALLBACK",
        "PROACTIVE_CALL",
    ],
}


class ChurnService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_latest_score_row(
        self, customer_id: uuid.UUID, org_id: uuid.UUID
    ) -> Optional[ChurnScore]:
        stmt = (
            select(ChurnScore)
            .where(
                ChurnScore.org_id == org_id,
                ChurnScore.entity_type == "CUSTOMER",
                ChurnScore.entity_id == customer_id,
            )
            .order_by(ChurnScore.score_timestamp.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_score(
        self, customer_id: str, org_id: uuid.UUID
    ) -> dict[str, Any]:
        cid = uuid.UUID(customer_id)
        row = await self.get_latest_score_row(cid, org_id)

        if row is not None:
            age_minutes = int(
                (datetime.now(timezone.utc) - row.score_timestamp).total_seconds() / 60
            )
            contributions = row.feature_contributions or []
            return {
                "customer_id": customer_id,
                "churn_probability": float(row.churn_probability),
                "risk_tier": row.risk_tier,
                "top_contributing_features": contributions,
                "recommended_interventions": INTERVENTIONS_BY_TIER.get(row.risk_tier, []),
                "score_age_minutes": age_minutes,
                "last_scored_at": row.score_timestamp.isoformat(),
                "model_version": row.model_version,
                "source": "churn_scores",
            }

        # Ownership check: fall back to customer metadata only within the org.
        customer = await self.db.get(Customer, cid)
        if customer is None or customer.org_id != org_id:
            raise ValueError(f"Customer {customer_id} not found")

        meta = customer.metadata_ or {}
        tier = str(meta.get("churn_tier", "LOW")).upper()
        probability = float(
            meta.get("churn_probability", TIER_DEFAULT_PROBABILITY.get(tier, 0.2))
        )

        return {
            "customer_id": customer_id,
            "churn_probability": probability,
            "risk_tier": tier,
            "top_contributing_features": [],
            "recommended_interventions": INTERVENTIONS_BY_TIER.get(tier, []),
            "score_age_minutes": 0,
            "last_scored_at": None,
            "model_version": None,
            "source": "customer_metadata",
        }
