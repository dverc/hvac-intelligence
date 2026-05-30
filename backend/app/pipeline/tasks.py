from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.ml.churn_schema import FEATURE_ORDER
from app.ml.feature_builder import FeatureBuilder
from app.ml.model_registry import get_churn_ensemble
from app.ml.sync_db import get_sync_session
from app.models.call_transcript import CallTranscript
from app.models.churn_score import ChurnScore
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.feature_store import FeatureStore
from app.pipeline.celery_app import celery_app
from app.core.metrics import saved_by_ai_counter
from app.pipeline.event_bus import (
    publish_batch_score_complete_sync,
    publish_intervention_complete_sync,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="app.pipeline.tasks.process_call_features", bind=True, max_retries=3)
def process_call_features(self, feature_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Deserialize Kafka payload, build rolling-window features, upsert feature_store,
    run churn ensemble when artifacts exist, persist churn_scores.
    """
    customer_id = feature_payload.get("customer_id")
    if not customer_id:
        logger.error("process_call_features missing customer_id")
        return {"status": "error", "reason": "missing customer_id"}

    entity_type = feature_payload.get("entity_type", "CUSTOMER")
    window_days = feature_payload.get("window_days")

    session = get_sync_session()
    try:
        builder = FeatureBuilder(session)
        full_features = builder.build(
            entity_id=customer_id,
            entity_type=entity_type,
            window_days=window_days,
        )
        meta = full_features.pop("_meta", {})
        model_input = FeatureBuilder.model_feature_dict(full_features)

        _upsert_feature_store(session, meta, full_features, model_input)
        session.commit()

        ensemble = get_churn_ensemble()
        prediction = ensemble.predict(model_input)

        if prediction.get("status") == "model_not_trained":
            logger.info("Skipping churn_scores persist — model not trained")
            session.commit()
            return {"status": "features_stored", "scoring": prediction}

        score_before = feature_payload.get("churn_risk_at_call_start")
        score_after = prediction.get("churn_probability")

        _persist_churn_score(session, meta, prediction, trigger="CALL_COMPLETED")
        _update_call_transcript_scores(
            session,
            call_id=feature_payload.get("call_id"),
            score_before=score_before,
            score_after=score_after,
        )
        session.commit()

        if (
            score_before is not None
            and score_after is not None
            and (float(score_before) - float(score_after)) >= 0.15
        ):
            saved_by_ai_counter.inc()
            _emit_intervention_complete(session, feature_payload, score_before, score_after)

        return {
            "status": "ok",
            "customer_id": str(customer_id),
            "churn_probability": prediction.get("churn_probability"),
            "risk_tier": prediction.get("risk_tier"),
        }
    except Exception as exc:
        session.rollback()
        logger.exception("process_call_features failed: %s", exc)
        raise self.retry(exc=exc, countdown=30)
    finally:
        session.close()


def _upsert_feature_store(
    session,
    meta: dict[str, Any],
    features: dict[str, Any],
    model_input: dict[str, Any],
) -> None:
    entity_type = meta["entity_type"]
    entity_id = uuid.UUID(meta["entity_id"])
    window_end = meta["window_end"]
    window_start = meta["window_start"]
    window_days = meta["window_days"]

    if isinstance(window_end, str):
        window_end = datetime.fromisoformat(window_end)
    if isinstance(window_start, str):
        window_start = datetime.fromisoformat(window_start)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)

    existing = session.execute(
        select(FeatureStore).where(
            FeatureStore.entity_type == entity_type,
            FeatureStore.entity_id == entity_id,
            FeatureStore.window_days == window_days,
            FeatureStore.window_end == window_end,
        )
    ).scalar_one_or_none()

    record = existing or FeatureStore(
        entity_type=entity_type,
        entity_id=entity_id,
        window_start=window_start,
        window_end=window_end,
        window_days=window_days,
    )

    _apply_feature_columns(record, features)
    record.feature_vector = [float(model_input.get(key, 0.0)) for key in FEATURE_ORDER[:64]]
    while len(record.feature_vector) < 64:
        record.feature_vector.append(0.0)

    if existing is None:
        session.add(record)
    session.flush()


def _apply_feature_columns(record: FeatureStore, features: dict[str, Any]) -> None:
    mapping = {
        "total_calls_window": "total_calls_window",
        "escalation_frequency": "escalation_frequency",
        "escalation_count": "escalation_count",
        "sentiment_first_call": "sentiment_first_call",
        "sentiment_last_call": "sentiment_last_call",
        "sentiment_degradation_slope": "sentiment_degradation_slope",
        "sentiment_std_dev": "sentiment_std_dev",
        "avg_sentiment_score": "avg_sentiment_score",
        "min_sentiment_score": "min_sentiment_score",
        "negative_call_ratio": "negative_call_ratio",
        "hesitation_marker_rate": "hesitation_marker_rate",
        "anger_emotion_ratio": "anger_emotion_ratio",
        "recurrence_complaint_count": "recurrence_complaint_count",
        "avg_time_to_resolution_hours": "avg_time_to_resolution_hours",
        "time_to_resolution_std_dev": "time_to_resolution_std_dev",
        "dispatch_cancellation_rate": "dispatch_cancellation_rate",
        "rescheduling_count": "rescheduling_count",
        "open_ticket_age_days_avg": "open_ticket_age_days_avg",
        "open_ticket_count": "open_ticket_count",
        "p1_p2_job_count": "p1_p2_job_count",
        "same_issue_recurrence_count": "same_issue_recurrence_count",
        "technician_change_count": "technician_change_count",
        "payment_delay_days_avg": "payment_delay_days_avg",
        "payment_failure_count": "payment_failure_count",
        "days_since_last_positive_call": "days_since_last_positive_call",
        "days_since_last_service": "days_since_last_service",
        "contract_days_until_renewal": "contract_days_until_renewal",
        "customer_rating_avg_90d": "customer_rating_avg_90d",
        "equipment_age_years": "equipment_age_years",
        "warranty_expired": "warranty_expired",
    }
    for source, target in mapping.items():
        value = features.get(source)
        if value is None:
            continue
        if isinstance(value, bool):
            setattr(record, target, value)
        elif isinstance(value, int) and "count" in target:
            setattr(record, target, value)
        else:
            setattr(record, target, Decimal(str(value)) if not isinstance(value, Decimal) else value)


def _persist_churn_score(
    session,
    meta: dict[str, Any],
    prediction: dict[str, Any],
    trigger: str,
) -> None:
    session.add(
        ChurnScore(
            entity_type=meta["entity_type"],
            entity_id=uuid.UUID(meta["entity_id"]),
            churn_probability=Decimal(str(prediction["churn_probability"])),
            risk_tier=prediction["risk_tier"],
            feature_contributions=prediction.get("feature_contributions"),
            model_version=prediction.get("model_version"),
            scoring_trigger=trigger,
            intervention_applied=trigger == "CALL_COMPLETED",
        )
    )


def _update_call_transcript_scores(
    session,
    *,
    call_id: str | None,
    score_before: Any,
    score_after: Any,
) -> None:
    if not call_id or score_after is None:
        return
    transcript = session.execute(
        select(CallTranscript).where(CallTranscript.call_id == call_id)
    ).scalar_one_or_none()
    if transcript is None:
        return
    if score_before is not None:
        transcript.churn_risk_at_call_start = Decimal(str(score_before))
    transcript.churn_risk_at_call_end = Decimal(str(score_after))
    if score_before is not None:
        transcript.intervention_successful = (
            float(score_before) - float(score_after)
        ) >= 0.15


def _emit_intervention_complete(
    session,
    feature_payload: dict[str, Any],
    score_before: Any,
    score_after: Any,
) -> None:
    customer_id = feature_payload.get("customer_id")
    call_id = feature_payload.get("call_id")
    customer = session.get(Customer, uuid.UUID(str(customer_id))) if customer_id else None

    job_number = None
    if call_id:
        transcript = session.execute(
            select(CallTranscript).where(CallTranscript.call_id == call_id)
        ).scalar_one_or_none()
        if transcript and transcript.dispatch_job_id:
            job = session.get(DispatchJob, transcript.dispatch_job_id)
            if job:
                job_number = job.job_number

    publish_intervention_complete_sync(
        {
            "call_id": call_id,
            "customer_id": customer_id,
            "customer_name": customer.full_name if customer else "Unknown",
            "score_before": round(float(score_before), 3),
            "score_after": round(float(score_after), 3),
            "delta": round(float(score_after) - float(score_before), 3),
            "intervention_type": feature_payload.get("intervention_type", "VOICE_RETENTION"),
            "saved_by_ai": True,
            "job_number": job_number,
        }
    )


@celery_app.task(name="app.pipeline.tasks.batch_rescore_customers")
def batch_rescore_customers() -> dict[str, Any]:
    """Batch re-score all active customers; emits BATCH_SCORE_COMPLETE on Redis."""
    session = get_sync_session()
    try:
        critical_before = _count_tier(session, "CRITICAL")
        customer_ids = session.scalars(
            select(Customer.customer_id).where(Customer.account_status == "ACTIVE")
        ).all()

        builder = FeatureBuilder(session)
        ensemble = get_churn_ensemble()
        scored = 0

        for customer_id in customer_ids:
            full_features = builder.build(entity_id=customer_id, entity_type="CUSTOMER")
            meta = full_features.pop("_meta", {})
            model_input = FeatureBuilder.model_feature_dict(full_features)
            _upsert_feature_store(session, meta, full_features, model_input)

            prediction = ensemble.predict(model_input)
            if prediction.get("status") != "model_not_trained":
                _persist_churn_score(session, meta, prediction, trigger="BATCH_RESCORE")
                scored += 1

        session.commit()
        critical_after = _count_tier(session, "CRITICAL")

        publish_batch_score_complete_sync(
            accounts_scored=scored,
            new_critical=max(0, critical_after - critical_before),
            resolved_critical=max(0, critical_before - critical_after),
        )

        return {
            "status": "ok",
            "accounts_scored": scored,
            "new_critical": max(0, critical_after - critical_before),
            "resolved_critical": max(0, critical_before - critical_after),
        }
    except Exception as exc:
        session.rollback()
        logger.exception("batch_rescore_customers failed: %s", exc)
        raise
    finally:
        session.close()


def _count_tier(session, tier: str) -> int:
    """Count customers at tier using latest churn_scores or metadata fallback."""
    from app.services.churn_service import TIER_DEFAULT_PROBABILITY

    rows = session.scalars(
        select(ChurnScore)
        .where(ChurnScore.entity_type == "CUSTOMER", ChurnScore.risk_tier == tier)
        .order_by(ChurnScore.score_timestamp.desc())
    ).all()
    if rows:
        return len({row.entity_id for row in rows})

    customers = session.scalars(
        select(Customer).where(Customer.account_status == "ACTIVE")
    ).all()
    count = 0
    for customer in customers:
        meta = customer.metadata_ or {}
        if str(meta.get("churn_tier", "LOW")).upper() == tier:
            count += 1
        elif tier == "LOW" and "churn_tier" not in meta:
            prob = float(meta.get("churn_probability", TIER_DEFAULT_PROBABILITY["LOW"]))
            if prob < 0.35:
                count += 1
    return count
