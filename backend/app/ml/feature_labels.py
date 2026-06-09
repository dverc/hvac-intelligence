"""Human-readable labels and explanation copy for ML features."""

from __future__ import annotations

FEATURE_FRIENDLY_NAMES: dict[str, str] = {
    "days_since_last_call": "Days Since Last Call",
    "days_since_last_service": "Days Since Last Service",
    "call_frequency_30d": "Call Frequency (30 days)",
    "call_frequency_90d": "Call Frequency (90 days)",
    "service_frequency_90d": "Service Frequency (90 days)",
    "total_calls_lifetime": "Total Calls",
    "contract_value_usd": "Contract Value",
    "avg_sentiment_score": "Average Sentiment",
    "sentiment_trend": "Sentiment Trend",
    "escalation_count_90d": "Escalations (90 days)",
    "escalation_frequency": "Escalation Rate",
    "tenure_days": "Customer Tenure",
    "is_annual_contract": "Annual Contract",
    "is_monthly_contract": "Monthly Contract",
    "payment_method_credit": "Credit Card Payment",
    "equipment_count": "Equipment Count",
    "has_old_equipment": "Has Old Equipment",
}


def friendly_name(feature: str) -> str:
    return FEATURE_FRIENDLY_NAMES.get(
        feature, feature.replace("_", " ").title()
    )


def shap_explanation_text(direction: str, shap_value: float) -> str:
    magnitude = abs(float(shap_value))
    if direction == "INCREASES_RISK":
        if magnitude > 0.1:
            return "Significantly increasing churn risk"
        return "Slightly increasing churn risk"
    if magnitude > 0.1:
        return "Significantly reducing churn risk"
    return "Slightly reducing churn risk"
