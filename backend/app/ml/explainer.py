"""SHAP-based feature attributions for churn predictions."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import shap

from app.ml.feature_engineering import ML_FEATURE_ORDER

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
    base_estimator = _underlying_lgbm(calibrated_model)
    if base_estimator is None:
        return []

    try:
        row = pd.DataFrame(
            [{key: float(feature_dict.get(key, 0.0)) for key in ML_FEATURE_ORDER}]
        )[ML_FEATURE_ORDER]
        explainer = shap.TreeExplainer(base_estimator)
        shap_values = explainer.shap_values(row)
        if isinstance(shap_values, list):
            values = shap_values[1][0] if len(shap_values) > 1 else shap_values[0][0]
        else:
            values = shap_values[0]

        ranked = sorted(
            zip(ML_FEATURE_ORDER, values),
            key=lambda item: abs(float(item[1])),
            reverse=True,
        )[:top_k]

        return [
            {
                "feature": feature,
                "shap_value": round(float(value), 4),
                "direction": "INCREASES_RISK" if float(value) > 0 else "DECREASES_RISK",
            }
            for feature, value in ranked
        ]
    except Exception as exc:
        logger.warning("SHAP explanation failed: %s", exc)
        return []
