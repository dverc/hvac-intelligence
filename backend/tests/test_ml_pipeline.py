from __future__ import annotations

import uuid
from datetime import date

import numpy as np
import pytest
from sklearn.calibration import CalibratedClassifierCV

from app.core.constants import SEED_ORG_ID
from app.ml.churn_model import (
    ChurnModelEnsemble,
    default_rule_score,
    predict_probability,
    train_model,
)
from app.ml.explainer import explain_prediction
from app.ml.feature_engineering import ML_FEATURE_ORDER, build_customer_features
from app.ml.model_registry import get_metrics, list_versions, load_model, models_dir, save_model
from app.models.customer import Customer


@pytest.mark.asyncio
async def test_feature_engineering_returns_all_expected_keys(db_session, seeded_customer):
    features = await build_customer_features(
        seeded_customer["customer_id"], db_session
    )
    assert set(features.keys()) == set(ML_FEATURE_ORDER)
    assert len(features) == len(ML_FEATURE_ORDER)
    for key in ML_FEATURE_ORDER:
        assert isinstance(features[key], float)


@pytest.mark.asyncio
async def test_feature_engineering_handles_missing_data(db_session):
    customer = Customer(
        org_id=SEED_ORG_ID,
        full_name="Empty Data Customer",
        phone_primary=f"+1555{uuid.uuid4().int % 100000000:08d}",
        customer_since=date(2024, 1, 1),
    )
    db_session.add(customer)
    await db_session.flush()

    features = await build_customer_features(customer.customer_id, db_session)

    assert features["avg_sentiment_score"] == 0.5
    assert features["total_calls_lifetime"] == 0.0
    assert features["escalation_count_90d"] == 0.0
    assert features["equipment_count"] == 0.0
    assert features["has_old_equipment"] == 0.0


def _synthetic_training_data(n: int = 12) -> list[tuple[dict, int]]:
    rows: list[tuple[dict, int]] = []
    rng = np.random.default_rng(42)
    for i in range(n):
        features = {
            key: float(rng.random()) for key in ML_FEATURE_ORDER
        }
        features["escalation_frequency"] = float(i % 3) / 3.0
        features["avg_sentiment_score"] = float(rng.random())
        label = 1 if features["escalation_frequency"] > 0.5 else 0
        rows.append((features, label))
    return rows


def test_model_prediction_returns_float_between_0_and_1():
    model, _ = train_model(_synthetic_training_data())
    sample = {key: 0.5 for key in ML_FEATURE_ORDER}
    prob = predict_probability(sample, model)
    assert isinstance(prob, float)
    assert 0.0 <= prob <= 1.0


def test_shap_explanations_return_correct_format():
    model, _ = train_model(_synthetic_training_data())
    sample = {key: 0.3 for key in ML_FEATURE_ORDER}
    contributions = explain_prediction(sample, model, top_k=5)

    assert len(contributions) <= 5
    for item in contributions:
        assert set(item.keys()) == {"feature", "shap_value", "direction"}
        assert item["feature"] in ML_FEATURE_ORDER
        assert item["direction"] in {"INCREASES_RISK", "DECREASES_RISK"}
        assert isinstance(item["shap_value"], float)


def test_shap_explanations_empty_when_no_model():
    sample = {key: 0.0 for key in ML_FEATURE_ORDER}
    assert explain_prediction(sample, None) == []


def test_model_registry_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr("app.ml.model_registry.models_dir", lambda: tmp_path)
    monkeypatch.setattr("app.ml.churn_model.models_dir", lambda: tmp_path)
    monkeypatch.setattr("app.ml.churn_model.load_model", lambda version="latest": load_model(version))

    training = _synthetic_training_data()
    model, metrics = train_model(training)
    version = "v_test_001"
    save_model(model, version, metrics)

    loaded = load_model(version)
    assert loaded is not None
    assert isinstance(loaded, CalibratedClassifierCV)

    stored_metrics = get_metrics(version)
    assert stored_metrics is not None
    assert stored_metrics["version"] == version
    assert "auc_roc" in stored_metrics

    versions = list_versions()
    assert version in versions or "latest" in versions


def test_default_scoring_when_no_model(monkeypatch, tmp_path):
    monkeypatch.setattr("app.ml.model_registry.models_dir", lambda: tmp_path)
    monkeypatch.setattr("app.ml.churn_model.models_dir", lambda: tmp_path)

    high_risk = {
        key: 0.0 for key in ML_FEATURE_ORDER
    }
    high_risk.update(
        {
            "escalation_frequency": 0.9,
            "escalation_count_90d": 5.0,
            "avg_sentiment_score": 0.1,
            "tenure_days": 30.0,
        }
    )
    low_risk = {key: 0.0 for key in ML_FEATURE_ORDER}
    low_risk.update(
        {
            "escalation_frequency": 0.0,
            "escalation_count_90d": 0.0,
            "avg_sentiment_score": 0.9,
            "tenure_days": 2000.0,
        }
    )

    assert predict_probability(high_risk, None) > predict_probability(low_risk, None)

    ensemble = ChurnModelEnsemble()
    legacy = ensemble.predict(high_risk)
    assert legacy["status"] == "model_not_trained"
    assert legacy["churn_probability"] is None
