"""Per-customer churn scoring pipeline (sync for Celery, async for API workers)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ml.churn_model import ChurnModelEnsemble, get_unified_score, score_to_tier
from app.ml.explainer import explain_prediction
from app.ml.feature_engineering import ML_FEATURE_ORDER, build_customer_features
from app.ml.feature_engineering import build_customer_features_sync
from app.ml.model_registry import get_churn_ensemble, get_metrics
from app.models.churn_score import ChurnScore
from app.models.customer import Customer

logger = logging.getLogger(__name__)


def _update_customer_metadata(
    customer: Customer,
    probability: float,
    tier: str,
) -> None:
    meta = dict(customer.metadata_ or {})
    meta["churn_probability"] = round(probability, 3)
    meta["churn_tier"] = tier
    meta["churn_risk_score"] = round(probability, 3)
    customer.metadata_ = meta


def _persist_score(
    session: Session,
    customer: Customer,
    prediction: dict[str, Any],
    trigger: str,
) -> ChurnScore:
    score = ChurnScore(
        entity_type="CUSTOMER",
        entity_id=customer.customer_id,
        org_id=customer.org_id,
        churn_probability=Decimal(str(prediction["churn_probability"])),
        risk_tier=prediction["risk_tier"],
        feature_contributions=prediction.get("feature_contributions"),
        model_version=prediction.get("model_version"),
        scoring_trigger=trigger,
        intervention_applied=trigger == "CALL_COMPLETED",
    )
    session.add(score)
    return score


def score_customer_sync(
    session: Session,
    customer_id: uuid.UUID,
    *,
    trigger: str = "BATCH_RESCORE",
    ensemble: ChurnModelEnsemble | None = None,
) -> dict[str, Any]:
    """
    Score one customer synchronously. Errors are contained per customer.
    """
    ensemble = ensemble or get_churn_ensemble()
    try:
        customer = session.get(Customer, customer_id)
        if customer is None:
            return {"status": "error", "reason": "customer_not_found"}

        features = build_customer_features_sync(customer_id, session)
        model = ensemble.calibrated_model if ensemble.is_ready else None
        metrics = get_metrics(ensemble.model_version) or {}
        probability, scoring_method = get_unified_score(features, model, metrics)
        prediction = {
            "status": "ok",
            "churn_probability": round(probability, 3),
            "risk_tier": score_to_tier(probability),
            "feature_contributions": (
                explain_prediction(features, model)
                if scoring_method == "ml_model" and model is not None
                else []
            ),
            "model_version": (
                metrics.get("version", ensemble.model_version)
                if scoring_method == "ml_model"
                else "rule_fallback_v1"
            ),
        }

        _update_customer_metadata(
            customer,
            float(prediction["churn_probability"]),
            prediction["risk_tier"],
        )
        _persist_score(session, customer, prediction, trigger)

        return {
            "status": prediction.get("status", "ok"),
            "customer_id": str(customer_id),
            "churn_probability": prediction["churn_probability"],
            "risk_tier": prediction["risk_tier"],
            "feature_contributions": prediction.get("feature_contributions", []),
            "features": {k: features[k] for k in ML_FEATURE_ORDER},
        }
    except Exception as exc:
        logger.exception("Churn scoring failed for customer %s: %s", customer_id, exc)
        return {
            "status": "error",
            "customer_id": str(customer_id),
            "reason": str(exc),
        }


async def score_customer_async(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    trigger: str = "API_RESCORE",
    ensemble: ChurnModelEnsemble | None = None,
) -> dict[str, Any]:
    """Async scoring path for FastAPI services."""
    ensemble = ensemble or get_churn_ensemble()
    try:
        customer = await db.get(Customer, customer_id)
        if customer is None:
            return {"status": "error", "reason": "customer_not_found"}

        features = await build_customer_features(customer_id, db)
        model = ensemble.calibrated_model if ensemble.is_ready else None
        metrics = get_metrics(ensemble.model_version) or {}
        probability, scoring_method = get_unified_score(features, model, metrics)
        prediction = {
            "status": "ok",
            "churn_probability": round(probability, 3),
            "risk_tier": score_to_tier(probability),
            "feature_contributions": (
                explain_prediction(features, model)
                if scoring_method == "ml_model" and model is not None
                else []
            ),
            "model_version": (
                metrics.get("version", ensemble.model_version)
                if scoring_method == "ml_model"
                else "rule_fallback_v1"
            ),
        }

        _update_customer_metadata(
            customer,
            float(prediction["churn_probability"]),
            prediction["risk_tier"],
        )
        score = ChurnScore(
            entity_type="CUSTOMER",
            entity_id=customer.customer_id,
            org_id=customer.org_id,
            churn_probability=Decimal(str(prediction["churn_probability"])),
            risk_tier=prediction["risk_tier"],
            feature_contributions=prediction.get("feature_contributions"),
            model_version=prediction.get("model_version"),
            scoring_trigger=trigger,
            score_timestamp=datetime.now(timezone.utc),
        )
        db.add(score)
        await db.flush()

        return {
            "status": prediction.get("status", "ok"),
            "customer_id": str(customer_id),
            "churn_probability": prediction["churn_probability"],
            "risk_tier": prediction["risk_tier"],
            "feature_contributions": prediction.get("feature_contributions", []),
            "features": {k: features[k] for k in ML_FEATURE_ORDER},
        }
    except Exception as exc:
        logger.exception("Async churn scoring failed for customer %s: %s", customer_id, exc)
        return {
            "status": "error",
            "customer_id": str(customer_id),
            "reason": str(exc),
        }
