from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit

from app.core.metrics import observe_churn_scoring
from app.ml.churn_schema import RISK_TIERS
from app.ml.explainer import explain_prediction
from app.ml.feature_engineering import ML_FEATURE_ORDER, _DEFAULT_FEATURES
from app.ml.model_registry import (
    DEFAULT_MODEL_VERSION,
    get_metrics,
    load_model,
    models_dir,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = models_dir() / "churn_model.pkl"


def default_rule_score(feature_dict: dict[str, Any]) -> float:
    """
    Heuristic fallback when no trained artifact exists.
    High escalations + low sentiment + short tenure → higher churn risk.
    """
    esc = float(feature_dict.get("escalation_frequency", 0.0))
    esc_count = float(feature_dict.get("escalation_count_90d", 0.0))
    sent = float(feature_dict.get("avg_sentiment_score", 0.5))
    tenure = float(feature_dict.get("tenure_days", 365.0))
    days_since_service = float(feature_dict.get("days_since_last_service", 365.0))
    call_freq = float(feature_dict.get("call_frequency_90d", 0.0))

    tenure_risk = 1.0 / (1.0 + tenure / 365.0)
    service_gap_risk = min(days_since_service / 730.0, 1.0)
    call_stress = min(call_freq / 10.0, 1.0)

    score = (
        0.25 * min(esc_count / 5.0, 1.0)
        + 0.20 * esc
        + 0.25 * (1.0 - sent)
        + 0.15 * tenure_risk
        + 0.10 * service_gap_risk
        + 0.05 * call_stress
    )
    return float(max(0.0, min(1.0, score)))


def _vectorize(feature_dict: dict[str, Any]) -> pd.DataFrame:
    row = {
        key: float(feature_dict.get(key, _DEFAULT_FEATURES.get(key, 0.0)))
        for key in ML_FEATURE_ORDER
    }
    return pd.DataFrame([row])[ML_FEATURE_ORDER]


def train_model(
    training_data: list[tuple[dict[str, Any], int]],
) -> tuple[CalibratedClassifierCV, dict[str, float]]:
    """
    Train a calibrated LightGBM churn classifier with time-series CV.
    Returns (model, metrics_dict).
    """
    if len(training_data) < 10:
        raise ValueError("Need at least 10 labeled samples to train churn model")

    X = pd.DataFrame(
        [
            {key: float(features.get(key, 0.0)) for key in ML_FEATURE_ORDER}
            for features, _ in training_data
        ]
    )[ML_FEATURE_ORDER]
    y = np.array([int(label) for _, label in training_data], dtype=int)

    lgbm_params = dict(
        objective="binary",
        n_estimators=50,
        learning_rate=0.1,
        num_leaves=15,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        verbose=-1,
        n_jobs=1,
        force_row_wise=True,
    )
    base = lgb.LGBMClassifier(**lgbm_params)

    tscv = TimeSeriesSplit(n_splits=5)
    fold_metrics: list[dict[str, float]] = []

    for train_idx, test_idx in tscv.split(X):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            continue
        fold_model = lgb.LGBMClassifier(**lgbm_params)
        fold_model.fit(X_train, y_train)
        probs = fold_model.predict_proba(X_test)[:, 1]
        preds = (probs >= 0.5).astype(int)
        fold_metrics.append(
            {
                "auc_roc": float(roc_auc_score(y_test, probs)),
                "precision": float(precision_score(y_test, preds, zero_division=0)),
                "recall": float(recall_score(y_test, preds, zero_division=0)),
                "f1": float(f1_score(y_test, preds, zero_division=0)),
                "accuracy": float(accuracy_score(y_test, preds)),
            }
        )

    if fold_metrics:
        metrics = {
            key: float(np.mean([m[key] for m in fold_metrics]))
            for key in fold_metrics[0]
        }
        logger.info(
            "TimeSeriesSplit CV metrics — AUC: %.3f, precision: %.3f, "
            "recall: %.3f, F1: %.3f",
            metrics["auc_roc"],
            metrics["precision"],
            metrics["recall"],
            metrics["f1"],
        )
    else:
        metrics = {
            "auc_roc": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "accuracy": 0.0,
        }
        logger.warning("TimeSeriesSplit produced no valid folds; training on full data")

    calibrated = CalibratedClassifierCV(base, method="isotonic", cv=3)
    calibrated.fit(X, y)
    return calibrated, metrics


def predict_probability(
    feature_dict: dict[str, Any],
    model: CalibratedClassifierCV | None = None,
) -> float:
    """Return calibrated churn probability in [0, 1]."""
    if model is None:
        model = load_model(DEFAULT_MODEL_VERSION)
    if model is None:
        return default_rule_score(feature_dict)

    df = _vectorize(feature_dict)
    prob = float(model.predict_proba(df)[0][1])
    return max(0.0, min(1.0, prob))


def score_to_tier(score: float) -> str:
    for tier, (low, high) in RISK_TIERS.items():
        if low <= score < high:
            return tier
    if score >= RISK_TIERS["CRITICAL"][0]:
        return "CRITICAL"
    return "LOW"


class ChurnModelEnsemble:
    """
    Production churn scorer — LightGBM + isotonic calibration with rule fallback.
    Preserves the legacy predict() response shape used by Celery and the API.
    """

    FEATURE_ORDER = ML_FEATURE_ORDER

    def __init__(self) -> None:
        self.model_version = DEFAULT_MODEL_VERSION
        self._model: CalibratedClassifierCV | None = None
        self._ready = False
        self._load()

    def _load(self) -> None:
        self._model = load_model(self.model_version)
        if self._model is not None:
            self._ready = True
            logger.info("Churn model loaded (version=%s)", self.model_version)
        else:
            logger.warning(
                "No churn model at %s — predict() returns model_not_trained",
                DEFAULT_MODEL_PATH,
            )

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def calibrated_model(self) -> CalibratedClassifierCV | None:
        return self._model

    @staticmethod
    def _score_to_tier(score: float) -> str:
        return score_to_tier(score)

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

        probability = predict_probability(feature_dict, self._model)
        tier = score_to_tier(probability)
        contributions = explain_prediction(feature_dict, self._model)

        metrics = get_metrics(self.model_version) or {}
        version_label = metrics.get("version", self.model_version)

        return {
            "status": "ok",
            "churn_probability": round(probability, 3),
            "risk_tier": tier,
            "feature_contributions": contributions,
            "model_version": version_label,
        }
