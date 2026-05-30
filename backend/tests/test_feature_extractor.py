import pytest

from app.ml.churn_schema import CHURN_FEATURE_SCHEMA, FEATURE_ORDER
from app.ml.feature_builder import FeatureBuilder
from app.pipeline.feature_extractor import FeatureExtractor
from app.pipeline.sentiment_analyzer import SentimentAnalyzer


@pytest.fixture
def extractor():
    return FeatureExtractor(SentimentAnalyzer())


def test_recurrence_detection(extractor, sample_transcript):
    """Verifies that 'third time' triggers recurrence_complaint_detected=True."""
    transcript = [
        {
            "speaker": "customer",
            "text": "This is the third time this has happened.",
            "words": [],
        }
    ]
    vector = extractor.extract("call_1", "cust_1", transcript, {"duration_seconds": 60})
    assert vector.recurrence_complaint_detected is True


def test_sentiment_slope_negative_call(extractor):
    """Sentiment degradation slope must be negative for a call that starts neutral and ends angry."""
    utterances = [
        {"speaker": "customer", "text": "Hi, I guess my AC is making a noise.", "words": []},
        {
            "speaker": "customer",
            "text": "It's been a week, nobody came, I'm very frustrated.",
            "words": [],
        },
        {
            "speaker": "customer",
            "text": "This is unacceptable, I want to cancel my contract.",
            "words": [],
        },
    ]
    vector = extractor.extract("call_2", "cust_2", utterances, {"duration_seconds": 180})
    assert vector.sentiment_degradation_slope < 0, "Slope should be negative for degrading sentiment"


def test_hesitation_marker_extraction(extractor):
    """Detects filler words in transcript."""
    utterances = [
        {
            "speaker": "customer",
            "text": "Um, yeah, uh, I don't know, like, it just stopped.",
            "words": [
                {"word": "Um", "start_ms": 0, "end_ms": 200},
                {"word": "yeah", "start_ms": 201, "end_ms": 400},
                {"word": "uh", "start_ms": 401, "end_ms": 600},
            ],
        }
    ]
    vector = extractor.extract("call_3", "cust_3", utterances, {"duration_seconds": 30})
    assert vector.filler_word_count >= 2


def test_all_34_features_present(sync_db_session, seeded_sync_customer):
    """Every CHURN_FEATURE_SCHEMA key is populated by FeatureBuilder.build()."""
    builder = FeatureBuilder(sync_db_session)
    features = builder.build(
        entity_id=seeded_sync_customer["customer_id"],
        entity_type="CUSTOMER",
        window_days=90,
    )
    model_features = FeatureBuilder.model_feature_dict(features)

    assert len(FEATURE_ORDER) == 34
    for key in CHURN_FEATURE_SCHEMA:
        assert key in model_features, f"Missing feature: {key}"
        assert model_features[key] is not None


def test_derived_features_computed(sync_db_session, seeded_sync_customer):
    """Derived interaction features are non-zero when inputs are non-zero."""
    builder = FeatureBuilder(sync_db_session)
    features = builder.build(
        entity_id=seeded_sync_customer["customer_id"],
        entity_type="CUSTOMER",
    )
    model_features = FeatureBuilder.model_feature_dict(features)

    assert model_features["escalation_frequency"] > 0
    assert model_features["avg_sentiment_score"] != 0
    assert model_features["sentiment_x_escalation"] != 0
    assert model_features["composite_risk_index"] != 0
    assert model_features["payment_x_sentiment"] != 0
    if model_features["same_issue_recurrence_count"] > 0:
        assert model_features["resolution_x_recurrence"] != 0
