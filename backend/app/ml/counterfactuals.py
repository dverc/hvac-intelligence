"""Counterfactual what-if explanations for churn risk reduction."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.churn_model import default_rule_score, predict_probability
from app.ml.explainer import compute_full_shap_contributions
from app.ml.feature_engineering import ML_FEATURE_ORDER, build_customer_features
from app.ml.feature_labels import friendly_name
from app.ml.model_registry import load_model


def _predict(features: dict[str, float], model: Any | None) -> float:
    if model is not None:
        return predict_probability(features, model)
    return default_rule_score(features)


def _suggest_improved_value(feature: str, current_value: float) -> float:
    if feature == "days_since_last_call":
        return float(min(current_value, 14))
    if feature == "days_since_last_service":
        return float(min(current_value, 14))
    if feature == "call_frequency_30d":
        return float(max(1, min(current_value, 2)))
    if feature == "escalation_count_90d":
        return float(max(0, min(current_value, 1)))
    if feature == "escalation_frequency":
        return float(max(0.0, current_value * 0.5))
    if feature == "avg_sentiment_score":
        return float(min(1.0, current_value + 0.2))
    if feature == "has_old_equipment":
        return 0.0
    if feature == "sentiment_trend":
        return float(min(1.0, current_value + 0.1))
    if feature in {"is_annual_contract", "payment_method_credit"}:
        return 1.0
    return float(current_value * 0.75) if current_value > 0 else current_value


def _suggested_action(feature: str, suggested_value: float) -> str:
    name = friendly_name(feature)
    if feature == "days_since_last_call":
        return f"Schedule a follow-up call within {int(suggested_value)} days"
    if feature == "days_since_last_service":
        return f"Schedule a maintenance visit within {int(suggested_value)} days"
    if feature == "call_frequency_30d":
        return f"Aim for {int(suggested_value)} check-in calls per month"
    if feature == "escalation_count_90d":
        return (
            f"Resolve open escalations — target {int(suggested_value)} or fewer "
            "in 90 days"
        )
    if feature == "escalation_frequency":
        return f"Reduce escalation rate to {suggested_value:.1%}"
    if feature == "avg_sentiment_score":
        return f"Improve service quality to achieve {suggested_value:.0%} positive sentiment"
    if feature == "has_old_equipment":
        return "Recommend equipment upgrade consultation"
    if feature == "is_annual_contract":
        return "Offer annual maintenance contract enrollment"
    return f"Improve {name} to {suggested_value:g}"


async def generate_counterfactuals(
    customer_id: uuid.UUID | str,
    db: AsyncSession,
    model: Any | None,
    current_features: dict[str, float] | None = None,
    current_score: float | None = None,
    target_score: float | None = None,
) -> dict[str, Any]:
    """Return top actionable counterfactual interventions to lower churn risk."""
    cid = uuid.UUID(str(customer_id))
    features = current_features or await build_customer_features(cid, db)
    score = current_score if current_score is not None else _predict(features, model)
    if target_score is None:
        target_score = max(score - 0.20, 0.10)
    else:
        target_score = max(float(target_score), 0.10)

    shap_rows = compute_full_shap_contributions(features, model)
    risk_features = [row for row in shap_rows if row["shap_value"] > 0]

    candidates: list[dict[str, Any]] = []
    for row in risk_features:
        feature = row["feature"]
        current_value = float(features.get(feature, 0.0))
        suggested_value = _suggest_improved_value(feature, current_value)
        if abs(suggested_value - current_value) < 1e-6:
            continue

        modified = dict(features)
        modified[feature] = suggested_value
        new_score = _predict(modified, model)
        reduction = max(0.0, score - new_score)
        if reduction <= 0:
            continue

        candidates.append(
            {
                "feature": feature,
                "friendly_name": friendly_name(feature),
                "current_value": round(current_value, 4),
                "suggested_value": round(suggested_value, 4),
                "suggested_action": _suggested_action(feature, suggested_value),
                "estimated_score_reduction": round(reduction, 4),
            }
        )

    candidates.sort(key=lambda item: item["estimated_score_reduction"], reverse=True)
    return {
        "customer_id": str(cid),
        "current_score": round(score, 4),
        "target_score": round(target_score, 4),
        "interventions": candidates[:3],
    }
