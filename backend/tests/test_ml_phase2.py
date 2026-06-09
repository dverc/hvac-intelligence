from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.ml.counterfactuals import generate_counterfactuals
from app.ml.feature_engineering import ML_FEATURE_ORDER
from app.ml.ground_truth import record_churn_event
from app.models.ground_truth_label import GroundTruthLabel


def _sample_features() -> dict[str, float]:
    features = {key: 0.0 for key in ML_FEATURE_ORDER}
    features.update(
        {
            "days_since_last_call": 45.0,
            "days_since_last_service": 120.0,
            "escalation_count_90d": 3.0,
            "escalation_frequency": 0.75,
            "avg_sentiment_score": 0.25,
            "tenure_days": 180.0,
            "has_old_equipment": 1.0,
        }
    )
    return features


@pytest.mark.asyncio
async def test_shap_explanation_endpoint_returns_correct_format(
    auth_client, seeded_customer
):
    customer_id = seeded_customer["customer_id"]
    mock_payload = {
        "customer_id": customer_id,
        "churn_probability": 0.85,
        "baseline_probability": 0.35,
        "features": [
            {
                "feature": "escalation_frequency",
                "friendly_name": "Escalation Rate",
                "value": 0.25,
                "shap_value": 0.18,
                "direction": "INCREASES_RISK",
                "explanation": "Significantly increasing churn risk",
            }
        ],
        "top_risk_factors": ["escalation_frequency"],
        "top_protective_factors": ["tenure_days"],
    }

    with patch(
        "app.api.v1.customers.build_shap_explanation",
        return_value=mock_payload,
    ):
        response = await auth_client.get(
            f"/api/v1/customers/{customer_id}/shap-explanation"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == customer_id
    assert body["churn_probability"] == 0.85
    assert body["baseline_probability"] == 0.35
    assert len(body["features"]) == 1
    feature = body["features"][0]
    assert feature["feature"] == "escalation_frequency"
    assert feature["friendly_name"] == "Escalation Rate"
    assert feature["direction"] == "INCREASES_RISK"
    assert "explanation" in feature
    assert body["top_risk_factors"] == ["escalation_frequency"]


@pytest.mark.asyncio
async def test_counterfactual_generation_returns_top_3(db_session, seeded_customer):
    features = _sample_features()
    mock_model = MagicMock()

    def fake_predict(feature_dict, model=None):
        score = 0.85
        if feature_dict.get("days_since_last_call", 45) <= 14:
            score -= 0.12
        if feature_dict.get("escalation_frequency", 0.75) <= 0.375:
            score -= 0.10
        if feature_dict.get("has_old_equipment", 1.0) == 0.0:
            score -= 0.06
        return max(0.0, min(1.0, score))

    shap_rows = [
        {
            "feature": "escalation_frequency",
            "value": 0.75,
            "shap_value": 0.2,
            "direction": "INCREASES_RISK",
        },
        {
            "feature": "days_since_last_call",
            "value": 45.0,
            "shap_value": 0.15,
            "direction": "INCREASES_RISK",
        },
        {
            "feature": "has_old_equipment",
            "value": 1.0,
            "shap_value": 0.08,
            "direction": "INCREASES_RISK",
        },
        {
            "feature": "tenure_days",
            "value": 180.0,
            "shap_value": -0.05,
            "direction": "DECREASES_RISK",
        },
    ]

    with (
        patch(
            "app.ml.counterfactuals.compute_full_shap_contributions",
            return_value=shap_rows,
        ),
        patch("app.ml.counterfactuals.predict_probability", side_effect=fake_predict),
        patch("app.ml.counterfactuals.default_rule_score", side_effect=fake_predict),
    ):
        result = await generate_counterfactuals(
            seeded_customer["customer_id"],
            db_session,
            mock_model,
            current_features=features,
            current_score=0.85,
        )

    assert len(result["interventions"]) <= 3
    assert len(result["interventions"]) >= 1
    first = result["interventions"][0]
    assert "feature" in first
    assert "friendly_name" in first
    assert "suggested_action" in first
    assert first["estimated_score_reduction"] > 0


@pytest.mark.asyncio
async def test_counterfactual_target_score_is_20_points_lower(
    db_session, seeded_customer
):
    features = _sample_features()
    with patch(
        "app.ml.counterfactuals.compute_full_shap_contributions",
        return_value=[],
    ):
        result = await generate_counterfactuals(
            seeded_customer["customer_id"],
            db_session,
            None,
            current_features=features,
            current_score=0.85,
        )

    assert result["current_score"] == 0.85
    assert result["target_score"] == pytest.approx(0.65)


@pytest.mark.asyncio
async def test_ground_truth_recording_saves_to_db(db_session, seeded_customer):
    label = await record_churn_event(
        seeded_customer["customer_id"],
        True,
        db_session,
        notes="Customer cancelled contract",
    )

    assert label.label_id is not None
    assert label.churned is True
    assert label.feature_snapshot
    assert float(label.churn_probability_at_time) >= 0.0

    stored = (
        await db_session.execute(
            select(GroundTruthLabel).where(
                GroundTruthLabel.label_id == label.label_id
            )
        )
    ).scalar_one()
    assert stored.notes == "Customer cancelled contract"


@pytest.mark.asyncio
async def test_churn_outcome_endpoint_returns_200(auth_client, seeded_customer):
    customer_id = seeded_customer["customer_id"]

    with patch("app.api.v1.customers.record_churn_event") as mock_record:
        mock_label = MagicMock()
        mock_label.label_id = "11111111-1111-4111-8111-111111111111"
        mock_label.churn_probability_at_time = 0.72
        mock_record.return_value = mock_label

        response = await auth_client.post(
            f"/api/v1/customers/{customer_id}/churn-outcome",
            json={"churned": False, "notes": "Retained after outreach"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["customer_id"] == customer_id
    assert body["churned"] is False
    assert body["label_id"] == "11111111-1111-4111-8111-111111111111"
