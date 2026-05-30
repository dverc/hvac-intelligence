import pytest

from app.ml.churn_model import ChurnModelEnsemble
from app.ml.churn_schema import FEATURE_ORDER


def test_missing_artifacts_graceful(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_ARTIFACTS_PATH", str(tmp_path))
    from app.core.config import get_settings
    from app.core.database import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()
    model = ChurnModelEnsemble()
    result = model.predict({key: 0.0 for key in FEATURE_ORDER})

    assert result["status"] == "model_not_trained"
    assert result["churn_probability"] is None
    assert not model.is_ready


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.349, "LOW"),
        (0.350, "MEDIUM"),
        (0.599, "MEDIUM"),
        (0.600, "HIGH"),
        (0.799, "HIGH"),
        (0.800, "CRITICAL"),
    ],
)
def test_score_to_tier_boundaries(score, expected):
    assert ChurnModelEnsemble._score_to_tier(score) == expected


def test_feature_vector_all_keys_validate(mock_churn_ensemble):
    feature_dict = {key: 0.1 for key in FEATURE_ORDER}
    assert len(feature_dict) == 34
    result = mock_churn_ensemble.predict(feature_dict)
    assert result["status"] == "ok"
    assert result["risk_tier"] == "HIGH"
