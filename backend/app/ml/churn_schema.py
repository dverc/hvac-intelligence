"""Churn model feature schema (§3.2) — shared constants without pipeline imports."""

from __future__ import annotations

CHURN_FEATURE_SCHEMA: dict[str, dict] = {
    "escalation_frequency": {"dtype": "float32", "range": [0.0, 1.0], "null_strategy": "fill_0"},
    "sentiment_degradation_slope": {"dtype": "float32", "range": [-2.0, 2.0], "null_strategy": "fill_0"},
    "avg_sentiment_score": {"dtype": "float32", "range": [-1.0, 1.0], "null_strategy": "fill_mean"},
    "min_sentiment_score": {"dtype": "float32", "range": [-1.0, 1.0], "null_strategy": "fill_mean"},
    "negative_call_ratio": {"dtype": "float32", "range": [0.0, 1.0], "null_strategy": "fill_0"},
    "anger_emotion_ratio": {"dtype": "float32", "range": [0.0, 1.0], "null_strategy": "fill_0"},
    "recurrence_complaint_count": {"dtype": "int16", "range": [0, 50], "null_strategy": "fill_0"},
    "hesitation_marker_rate": {"dtype": "float32", "range": [0.0, 5.0], "null_strategy": "fill_0"},
    "sentiment_std_dev": {"dtype": "float32", "range": [0.0, 2.0], "null_strategy": "fill_0"},
    "sentiment_first_call": {"dtype": "float32", "range": [-1.0, 1.0], "null_strategy": "fill_mean"},
    "sentiment_last_call": {"dtype": "float32", "range": [-1.0, 1.0], "null_strategy": "fill_mean"},
    "avg_time_to_resolution_hours": {"dtype": "float32", "range": [0.0, 720.0], "null_strategy": "fill_mean"},
    "time_to_resolution_std_dev": {"dtype": "float32", "range": [0.0, 500.0], "null_strategy": "fill_0"},
    "dispatch_cancellation_rate": {"dtype": "float32", "range": [0.0, 1.0], "null_strategy": "fill_0"},
    "rescheduling_count": {"dtype": "int16", "range": [0, 20], "null_strategy": "fill_0"},
    "open_ticket_age_days_avg": {"dtype": "float32", "range": [0.0, 365.0], "null_strategy": "fill_0"},
    "open_ticket_count": {"dtype": "int16", "range": [0, 30], "null_strategy": "fill_0"},
    "p1_p2_job_count": {"dtype": "int16", "range": [0, 20], "null_strategy": "fill_0"},
    "same_issue_recurrence_count": {"dtype": "int16", "range": [0, 20], "null_strategy": "fill_0"},
    "technician_change_count": {"dtype": "int16", "range": [0, 15], "null_strategy": "fill_0"},
    "total_calls_window": {"dtype": "int16", "range": [0, 200], "null_strategy": "fill_0"},
    "payment_delay_days_avg": {"dtype": "float32", "range": [0.0, 180.0], "null_strategy": "fill_0"},
    "payment_failure_count": {"dtype": "int16", "range": [0, 20], "null_strategy": "fill_0"},
    "days_since_last_positive_call": {"dtype": "int16", "range": [0, 365], "null_strategy": "fill_365"},
    "days_since_last_service": {"dtype": "int16", "range": [0, 730], "null_strategy": "fill_730"},
    "contract_days_until_renewal": {"dtype": "int16", "range": [-365, 730], "null_strategy": "fill_0"},
    "equipment_age_years": {"dtype": "float32", "range": [0.0, 30.0], "null_strategy": "fill_mean"},
    "warranty_expired": {"dtype": "bool", "range": [0, 1], "null_strategy": "fill_0"},
    "customer_rating_avg_90d": {"dtype": "float32", "range": [1.0, 5.0], "null_strategy": "fill_mean"},
    "escalation_count": {"dtype": "int16", "range": [0, 50], "null_strategy": "fill_0"},
    "sentiment_x_escalation": {
        "dtype": "float32",
        "computed": "avg_sentiment_score * escalation_frequency",
    },
    "resolution_x_recurrence": {
        "dtype": "float32",
        "computed": "avg_time_to_resolution_hours * same_issue_recurrence_count",
    },
    "payment_x_sentiment": {
        "dtype": "float32",
        "computed": "payment_failure_count * (1 + abs(min_sentiment_score))",
    },
    "composite_risk_index": {
        "dtype": "float32",
        "computed": "(negative_call_ratio * 0.3) + (escalation_frequency * 0.4) + (sentiment_degradation_slope * -0.3)",
    },
}

FEATURE_ORDER: list[str] = list(CHURN_FEATURE_SCHEMA.keys())

RISK_TIERS: dict[str, tuple[float, float]] = {
    "LOW": (0.000, 0.350),
    "MEDIUM": (0.350, 0.600),
    "HIGH": (0.600, 0.800),
    "CRITICAL": (0.800, 1.000),
}

ENSEMBLE_WEIGHTS: dict[str, float] = {
    "xgboost": 0.55,
    "lightgbm": 0.35,
    "isolation_forest": 0.10,
}
