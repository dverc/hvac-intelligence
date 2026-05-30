from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.core.metrics import observe_churn_scoring
from app.ml.churn_schema import ENSEMBLE_WEIGHTS, FEATURE_ORDER, RISK_TIERS

logger = logging.getLogger(__name__)


class ChurnModelEnsemble:
    """
    Loads and runs the XGBoost + LightGBM ensemble for churn probability prediction.
    Artifacts loaded from MODEL_ARTIFACTS_PATH at startup.
    """

    FEATURE_ORDER = FEATURE_ORDER
    ENSEMBLE_WEIGHTS = ENSEMBLE_WEIGHTS

    def __init__(self) -> None:
        settings = get_settings()
        artifacts_path = Path(settings.MODEL_ARTIFACTS_PATH)
        self.model_version = "ensemble_v1.0.0"
        self._ready = False
        self.xgb_model = None
        self.lgbm_model = None
        self.isolation_forest = None
        self.scaler = None
        self.shap_explainer = None

        required = [
            "xgb_churn_model.pkl",
            "lgbm_churn_model.pkl",
            "isolation_forest.pkl",
            "feature_scaler.pkl",
            "shap_explainer_xgb.pkl",
        ]
        missing = [name for name in required if not (artifacts_path / name).exists()]
        if missing:
            logger.warning(
                "Churn model artifacts missing at %s (%s). predict() returns model_not_trained.",
                artifacts_path,
                ", ".join(missing),
            )
            return

        try:
            with open(artifacts_path / "xgb_churn_model.pkl", "rb") as handle:
                self.xgb_model = pickle.load(handle)
            with open(artifacts_path / "lgbm_churn_model.pkl", "rb") as handle:
                self.lgbm_model = pickle.load(handle)
            with open(artifacts_path / "isolation_forest.pkl", "rb") as handle:
                self.isolation_forest = pickle.load(handle)
            with open(artifacts_path / "feature_scaler.pkl", "rb") as handle:
                self.scaler = pickle.load(handle)
            with open(artifacts_path / "shap_explainer_xgb.pkl", "rb") as handle:
                self.shap_explainer = pickle.load(handle)
            self._ready = True
            logger.info("Churn model ensemble loaded from %s", artifacts_path)
        except Exception as exc:
            logger.warning("Failed to load churn model artifacts: %s", exc, exc_info=True)
            self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    def predict(self, feature_dict: dict[str, Any]) -> dict[str, Any]:
        with observe_churn_scoring():
            return self._predict_impl(feature_dict)

    def _predict_impl(self, feature_dict: dict[str, Any]) -> dict[str, Any]:
        if not self._ready:
            return {
                "status": "model_not_trained",
                "message": "Model artifacts not found or failed to load",
                "churn_probability": None,
                "risk_tier": None,
                "feature_contributions": [],
                "model_version": None,
            }

        df = pd.DataFrame([{key: feature_dict.get(key, 0) for key in self.FEATURE_ORDER}])[
            self.FEATURE_ORDER
        ]
        df_scaled = self.scaler.transform(df)

        xgb_prob = float(self.xgb_model.predict_proba(df_scaled)[0][1])
        lgbm_prob = float(self.lgbm_model.predict_proba(df_scaled)[0][1])

        iso_score = float(self.isolation_forest.score_samples(df_scaled)[0])
        iso_normalized = float(1 - (iso_score - (-0.5)) / (0.5 - (-0.5)))
        iso_normalized = max(0.0, min(1.0, iso_normalized))

        ensemble_prob = (
            xgb_prob * self.ENSEMBLE_WEIGHTS["xgboost"]
            + lgbm_prob * self.ENSEMBLE_WEIGHTS["lightgbm"]
            + iso_normalized * self.ENSEMBLE_WEIGHTS["isolation_forest"]
        )
        ensemble_prob = float(max(0.0, min(1.0, ensemble_prob)))

        shap_values = self.shap_explainer(df_scaled)
        raw_shap = shap_values.values[0].tolist()
        top_features = sorted(
            zip(self.FEATURE_ORDER, raw_shap),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[:5]

        risk_tier = self._score_to_tier(ensemble_prob)

        return {
            "status": "ok",
            "churn_probability": round(ensemble_prob, 3),
            "risk_tier": risk_tier,
            "feature_contributions": [
                {
                    "feature": feature,
                    "shap_value": round(value, 4),
                    "direction": "INCREASES_RISK" if value > 0 else "DECREASES_RISK",
                }
                for feature, value in top_features
            ],
            "model_version": self.model_version,
        }

    @staticmethod
    def _score_to_tier(score: float) -> str:
        for tier, (low, high) in RISK_TIERS.items():
            if low <= score < high:
                return tier
        if score >= RISK_TIERS["CRITICAL"][0]:
            return "CRITICAL"
        return "LOW"
