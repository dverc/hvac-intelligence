from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.ml.churn_model import default_rule_score, get_unified_score
from app.ml.drift_monitor import compute_psi, get_drift_status
from app.ml.feature_engineering import ML_FEATURE_ORDER
from app.ml.retraining import check_and_trigger_retraining


def _sample_features() -> dict[str, float]:
    features = {key: 0.0 for key in ML_FEATURE_ORDER}
    features.update(
        {
            "escalation_count_90d": 3.0,
            "escalation_frequency": 0.75,
            "avg_sentiment_score": 0.25,
            "tenure_days": 180.0,
        }
    )
    return features


def test_unified_score_uses_rule_based_when_auc_low():
    features = _sample_features()
    mock_model = MagicMock()
    metrics = {"auc_roc": 0.5}

    score, method = get_unified_score(features, mock_model, metrics)

    assert method == "rule_based"
    assert score == default_rule_score(features)
    mock_model.predict_proba.assert_not_called()


def test_unified_score_uses_ml_when_auc_high():
    features = _sample_features()
    mock_model = MagicMock()
    mock_model.predict_proba.return_value = [[0.2, 0.62]]
    metrics = {"auc_roc": 0.8}

    score, method = get_unified_score(features, mock_model, metrics)

    assert method == "ml_model"
    assert score == pytest.approx(0.62)
    mock_model.predict_proba.assert_called_once()


def test_psi_computation_stable():
    rng = np.random.default_rng(42)
    expected = rng.normal(0.35, 0.08, 500).clip(0.0, 1.0).tolist()
    actual = rng.normal(0.36, 0.08, 500).clip(0.0, 1.0).tolist()

    psi = compute_psi(expected, actual)

    assert psi < 0.1


def test_psi_computation_drift():
    expected = [0.1] * 100
    actual = [0.9] * 100

    psi = compute_psi(expected, actual)

    assert psi > 0.2


def test_drift_status_thresholds():
    assert get_drift_status(0.05) == "STABLE"
    assert get_drift_status(0.15) == "MONITOR"
    assert get_drift_status(0.25) == "RETRAIN"


def test_retraining_not_triggered_insufficient_ground_truth():
    mock_db = MagicMock()
    mock_db.scalar.return_value = 5

    with patch(
        "app.ml.retraining.check_model_drift",
        return_value={
            "psi": 0.35,
            "status": "RETRAIN",
            "needs_retraining": True,
        },
    ):
        result = check_and_trigger_retraining(mock_db)

    assert result["triggered"] is False
    assert result["reason"] == "insufficient_ground_truth"
    assert result["psi"] == pytest.approx(0.35)


@pytest.mark.asyncio
async def test_model_health_endpoint_returns_correct_format(auth_client):
    mock_drift = {
        "psi": 0.05,
        "status": "STABLE",
        "needs_retraining": False,
        "checked_at": "2026-06-09T12:00:00+00:00",
        "model_version": "v1",
        "recent_score_count": 12,
    }
    mock_metrics = {
        "version": "v1",
        "auc_roc": 0.5,
    }

    mock_ensemble = MagicMock()
    mock_ensemble.is_ready = True
    mock_ensemble.calibrated_model = MagicMock()

    with (
        patch("app.api.v1.ml.get_metrics", return_value=mock_metrics),
        patch("app.api.v1.ml.get_churn_ensemble", return_value=mock_ensemble),
        patch(
            "app.api.v1.ml.check_model_drift_async",
            return_value=mock_drift,
        ),
    ):
        response = await auth_client.get("/api/v1/ml/model-health")

    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == "v1"
    assert body["model_quality"] == "rule_based"
    assert body["auc_roc"] == 0.5
    assert body["drift_status"] == "STABLE"
    assert body["psi"] == 0.05
    assert body["needs_retraining"] is False
    assert body["last_checked"] == "2026-06-09T12:00:00+00:00"
    assert body["scoring_method"] == "rule_based"
    assert "total_scores_30d" in body
    assert "ground_truth_labels_count" in body
