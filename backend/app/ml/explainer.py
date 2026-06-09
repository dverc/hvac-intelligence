"""SHAP-based feature attributions for churn predictions."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import shap

from app.ml.feature_engineering import ML_FEATURE_ORDER, _DEFAULT_FEATURES
from app.ml.feature_labels import friendly_name, shap_explanation_text

logger = logging.getLogger(__name__)


def _underlying_lgbm(calibrated_model: Any) -> Any | None:
    if calibrated_model is None:
        return None
    if hasattr(calibrated_model, "calibrated_classifiers_"):
        estimators = calibrated_model.calibrated_classifiers_
        if estimators:
            return estimators[0].estimator
    if hasattr(calibrated_model, "estimators_") and calibrated_model.estimators_:
        return calibrated_model.estimators_[0]
    return calibrated_model


def _extract_shap_values(
    explainer: shap.TreeExplainer,
    row: pd.DataFrame,
) -> tuple[np.ndarray, float]:
    shap_values = explainer.shap_values(row)
    if isinstance(shap_values, list):
        values = shap_values[1][0] if len(shap_values) > 1 else shap_values[0][0]
    else:
        values = shap_values[0]

    expected = explainer.expected_value
    if isinstance(expected, (list, np.ndarray)):
        baseline = float(expected[1] if len(expected) > 1 else expected[0])
    else:
        baseline = float(expected)
    return np.asarray(values, dtype=float), baseline


def compute_full_shap_contributions(
    feature_dict: dict[str, float],
    calibrated_model: Any | None,
) -> list[dict[str, Any]]:
    """Return SHAP contributions for every feature, sorted by |SHAP|."""
    base_estimator = _underlying_lgbm(calibrated_model)
    if base_estimator is None:
        return []

    try:
        row = pd.DataFrame(
            [{key: float(feature_dict.get(key, 0.0)) for key in ML_FEATURE_ORDER}]
        )[ML_FEATURE_ORDER]
        explainer = shap.TreeExplainer(base_estimator, model_output="probability")
        values, _ = _extract_shap_values(explainer, row)

        rows = [
            {
                "feature": feature,
                "value": float(feature_dict.get(feature, 0.0)),
                "shap_value": round(float(shap_val), 4),
                "direction": "INCREASES_RISK"
                if float(shap_val) > 0
                else "DECREASES_RISK",
            }
            for feature, shap_val in zip(ML_FEATURE_ORDER, values)
        ]
        rows.sort(key=lambda item: abs(item["shap_value"]), reverse=True)
        return rows
    except Exception as exc:
        logger.warning("Full SHAP computation failed: %s", exc)
        return []


def build_shap_explanation(
    customer_id: str,
    feature_dict: dict[str, float],
    calibrated_model: Any | None,
) -> dict[str, Any]:
    """Build the full SHAP waterfall API response."""
    from app.ml.churn_model import default_rule_score, predict_probability

    churn_probability = (
        predict_probability(feature_dict, calibrated_model)
        if calibrated_model is not None
        else default_rule_score(feature_dict)
    )

    base_estimator = _underlying_lgbm(calibrated_model)
    baseline_probability = default_rule_score(
        {key: _DEFAULT_FEATURES[key] for key in ML_FEATURE_ORDER}
    )

    feature_rows: list[dict[str, Any]] = []
    if base_estimator is not None:
        try:
            row = pd.DataFrame(
                [{key: float(feature_dict.get(key, 0.0)) for key in ML_FEATURE_ORDER}]
            )[ML_FEATURE_ORDER]
            explainer = shap.TreeExplainer(base_estimator, model_output="probability")
            values, baseline_probability = _extract_shap_values(explainer, row)
            baseline_probability = float(max(0.0, min(1.0, baseline_probability)))

            for feature, shap_val in zip(ML_FEATURE_ORDER, values):
                direction = "INCREASES_RISK" if float(shap_val) > 0 else "DECREASES_RISK"
                feature_rows.append(
                    {
                        "feature": feature,
                        "friendly_name": friendly_name(feature),
                        "value": round(float(feature_dict.get(feature, 0.0)), 4),
                        "shap_value": round(float(shap_val), 4),
                        "direction": direction,
                        "explanation": shap_explanation_text(direction, float(shap_val)),
                    }
                )
            feature_rows.sort(key=lambda item: abs(item["shap_value"]), reverse=True)
        except Exception as exc:
            logger.warning("SHAP explanation build failed: %s", exc)

    top_risk_factors = [
        row["feature"] for row in feature_rows if row["direction"] == "INCREASES_RISK"
    ][:5]
    top_protective_factors = [
        row["feature"] for row in feature_rows if row["direction"] == "DECREASES_RISK"
    ][:5]

    return {
        "customer_id": customer_id,
        "churn_probability": round(float(churn_probability), 4),
        "baseline_probability": round(float(baseline_probability), 4),
        "features": feature_rows,
        "top_risk_factors": top_risk_factors,
        "top_protective_factors": top_protective_factors,
    }


def explain_prediction(
    feature_dict: dict[str, float],
    calibrated_model: Any | None,
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Return top features by |SHAP| for a single prediction.
    Format matches dashboard: [{feature, shap_value, direction}].
    """
    rows = compute_full_shap_contributions(feature_dict, calibrated_model)
    return [
        {
            "feature": row["feature"],
            "shap_value": row["shap_value"],
            "direction": row["direction"],
        }
        for row in rows[:top_k]
    ]
