from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select, text

from app.ml.churn_schema import FEATURE_ORDER
from app.ml.feature_builder import FeatureBuilder
from app.ml.model_registry import get_churn_ensemble
from app.pipeline.churn_scorer import score_customer_sync
from app.ml.sync_db import get_sync_session
from app.models.call_transcript import CallTranscript
from app.models.churn_score import ChurnScore
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.feature_store import FeatureStore
from app.models.google_calendar_token import GoogleCalendarToken
from app.models.jobber_token import JobberToken
from app.models.organization import Organization
from app.models.technician import Technician
from app.pipeline.celery_app import celery_app
from app.core.metrics import saved_by_ai_counter
from app.services.sms_service import SmsService, send_sms
from app.services.email_service import build_weekly_report_html, send_email
from app.pipeline.event_bus import (
    publish_batch_score_complete_sync,
    publish_intervention_complete_sync,
)

logger = logging.getLogger(__name__)

_STANDARD_TASK_RETRY = dict(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)

_SMS_TASK_RETRY = dict(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)


@celery_app.task(name="app.pipeline.tasks.process_call_features", **_STANDARD_TASK_RETRY)
def process_call_features(self, feature_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Deserialize Kafka payload, build rolling-window features, upsert feature_store,
    run churn ensemble when artifacts exist, persist churn_scores.
    """
    logger.info(
        "Task starting: process_call_features attempt=%s",
        self.request.retries + 1,
    )
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
        scoring = score_customer_sync(
            session,
            uuid.UUID(str(customer_id)),
            trigger="CALL_COMPLETED",
            ensemble=ensemble,
        )

        if scoring.get("status") == "error":
            logger.warning(
                "Churn scoring failed for customer %s: %s",
                customer_id,
                scoring.get("reason"),
            )
            session.commit()
            return {"status": "features_stored", "scoring": scoring}

        score_before = feature_payload.get("churn_risk_at_call_start")
        score_after = scoring.get("churn_probability")

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
            "churn_probability": scoring.get("churn_probability"),
            "risk_tier": scoring.get("risk_tier"),
        }
    except Exception as exc:
        session.rollback()
        logger.exception("process_call_features failed: %s", exc)
        raise self.retry(exc=exc, countdown=30)
    finally:
        session.close()


def _resolve_entity_org_id(session, entity_type: str, entity_id: uuid.UUID):
    """Derive the owning org for a scored entity so scoring rows are tenant-correct.

    Falls back to the column server_default (seed org) only if the entity is gone.
    """
    if entity_type == "EMPLOYEE":
        tech = session.get(Technician, entity_id)
        return tech.org_id if tech is not None else None
    customer = session.get(Customer, entity_id)
    return customer.org_id if customer is not None else None


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
    if existing is None:
        org_id = _resolve_entity_org_id(session, entity_type, entity_id)
        if org_id is not None:
            record.org_id = org_id

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
    entity_type = meta["entity_type"]
    entity_id = uuid.UUID(meta["entity_id"])
    org_id = _resolve_entity_org_id(session, entity_type, entity_id)
    score = ChurnScore(
        entity_type=entity_type,
        entity_id=entity_id,
        churn_probability=Decimal(str(prediction["churn_probability"])),
        risk_tier=prediction["risk_tier"],
        feature_contributions=prediction.get("feature_contributions"),
        model_version=prediction.get("model_version"),
        scoring_trigger=trigger,
        intervention_applied=trigger == "CALL_COMPLETED",
    )
    if org_id is not None:
        score.org_id = org_id
    session.add(score)


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


@celery_app.task(name="app.pipeline.tasks.batch_rescore_customers", **_STANDARD_TASK_RETRY)
def batch_rescore_customers(self) -> dict[str, Any]:
    """Batch re-score all active customers; emits BATCH_SCORE_COMPLETE on Redis."""
    logger.info(
        "Task starting: batch_rescore_customers attempt=%s",
        self.request.retries + 1,
    )
    session = get_sync_session()
    try:
        critical_before = _count_tier(session, "CRITICAL")
        customer_ids = session.scalars(
            select(Customer.customer_id).where(Customer.account_status == "ACTIVE")
        ).all()

        builder = FeatureBuilder(session)
        ensemble = get_churn_ensemble()
        scored = 0
        errors = 0

        for customer_id in customer_ids:
            try:
                full_features = builder.build(
                    entity_id=customer_id, entity_type="CUSTOMER"
                )
                meta = full_features.pop("_meta", {})
                model_input = FeatureBuilder.model_feature_dict(full_features)
                _upsert_feature_store(session, meta, full_features, model_input)
            except Exception as exc:
                logger.warning(
                    "Feature store upsert failed for customer %s: %s",
                    customer_id,
                    exc,
                )

            result = score_customer_sync(
                session,
                customer_id,
                trigger="BATCH_RESCORE",
                ensemble=ensemble,
            )
            if result.get("status") in {"ok", "model_not_trained"}:
                scored += 1
            elif result.get("status") == "error":
                errors += 1

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
            "scoring_errors": errors,
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


@celery_app.task(name="app.pipeline.tasks.sync_technician_schedules", **_STANDARD_TASK_RETRY)
def sync_technician_schedules(self) -> dict[str, Any]:
    """Advance stale SCHEDULED jobs whose window has passed (FSM sync foundation)."""
    logger.info(
        "Task starting: sync_technician_schedules attempt=%s",
        self.request.retries + 1,
    )
    session = get_sync_session()
    try:
        now = datetime.now(timezone.utc)
        orgs = session.scalars(
            select(Organization).where(Organization.is_active.is_(True))
        ).all()
        summaries: list[str] = []
        total_updated = 0

        for org in orgs:
            jobs = session.scalars(
                select(DispatchJob).where(
                    DispatchJob.org_id == org.org_id,
                    DispatchJob.job_status == "SCHEDULED",
                    DispatchJob.scheduled_window_start.isnot(None),
                    DispatchJob.scheduled_window_start < now,
                )
            ).all()
            updated = 0
            for job in jobs:
                job.job_status = "IN_PROGRESS"
                updated += 1
            if updated:
                summaries.append(f"{org.org_name} — {updated} jobs updated")
                logger.info(
                    "Schedule sync: %s — %s jobs updated", org.org_name, updated
                )
            total_updated += updated

        session.commit()
        return {
            "status": "ok",
            "jobs_updated": total_updated,
            "summaries": summaries,
        }
    except Exception as exc:
        session.rollback()
        logger.exception("sync_technician_schedules failed: %s", exc)
        raise
    finally:
        session.close()


@celery_app.task(name="app.pipeline.tasks.sync_google_calendars", **_STANDARD_TASK_RETRY)
def sync_google_calendars(self) -> dict[str, Any]:
    """Sync external Google Calendar events into schedule overrides (Phase 8A)."""
    logger.info(
        "Task starting: sync_google_calendars attempt=%s",
        self.request.retries + 1,
    )
    return asyncio.run(_sync_google_calendars_async())


async def _sync_google_calendars_async() -> dict[str, Any]:
    from app.core.database import get_session_factory
    from app.services.google_calendar_service import GoogleCalendarService

    date_from = date.today()
    date_to = date_from + timedelta(days=14)
    summaries: list[str] = []
    total_synced = 0

    async with get_session_factory()() as session:
        try:
            tokens = (
                await session.execute(
                    select(GoogleCalendarToken).where(
                        GoogleCalendarToken.is_active.is_(True),
                        GoogleCalendarToken.technician_id.isnot(None),
                    )
                )
            ).scalars().all()

            gcal = GoogleCalendarService(session)
            org_counts: dict[uuid.UUID, int] = {}

            for token in tokens:
                if token.technician_id is None:
                    continue
                try:
                    count = await gcal.sync_calendar_to_availability(
                        token.org_id,
                        token.technician_id,
                        date_from,
                        date_to,
                    )
                    org_counts[token.org_id] = org_counts.get(token.org_id, 0) + count
                    total_synced += count
                except Exception as exc:
                    logger.warning(
                        "GCal sync failed for org=%s tech=%s: %s",
                        token.org_id,
                        token.technician_id,
                        exc,
                    )

            org_names: dict[uuid.UUID, str] = {}
            for org_id in org_counts:
                org = await session.get(Organization, org_id)
                org_names[org_id] = org.org_name if org else str(org_id)

            for org_id, count in org_counts.items():
                name = org_names.get(org_id, str(org_id))
                summaries.append(f"GCal sync: {name} — {count} events synced")
                logger.info("GCal sync: %s — %s events synced", name, count)

            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {
        "status": "ok",
        "events_synced": total_synced,
        "summaries": summaries,
    }


@celery_app.task(name="app.pipeline.tasks.sync_jobber_data", **_STANDARD_TASK_RETRY)
def sync_jobber_data(self) -> dict[str, Any]:
    """Sync Jobber clients, users, and jobs into local tables (Phase 8B)."""
    logger.info(
        "Task starting: sync_jobber_data attempt=%s",
        self.request.retries + 1,
    )
    return asyncio.run(_sync_jobber_data_async())


async def _sync_jobber_data_async() -> dict[str, Any]:
    from app.core.database import get_session_factory
    from app.services.jobber_service import JobberService

    summaries: list[str] = []

    async with get_session_factory()() as session:
        try:
            tokens = (
                await session.execute(
                    select(JobberToken).where(JobberToken.is_active.is_(True))
                )
            ).scalars().all()

            jobber = JobberService(session)
            for token in tokens:
                try:
                    clients = await jobber.sync_clients_to_customers(token.org_id)
                    users = await jobber.sync_users_to_technicians(token.org_id)
                    jobs = await jobber.sync_jobs_to_dispatch(token.org_id)
                    await jobber.mark_sync_completed(token.org_id)
                    org = await session.get(Organization, token.org_id)
                    name = org.org_name if org else str(token.org_id)
                    summary = (
                        f"Jobber sync: {name} — "
                        f"clients:{clients} users:{users} jobs:{jobs}"
                    )
                    summaries.append(summary)
                    logger.info(summary)
                except Exception as exc:
                    logger.warning(
                        "Jobber sync failed for org=%s: %s", token.org_id, exc
                    )

            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {"status": "ok", "summaries": summaries}


@celery_app.task(name="app.pipeline.tasks.send_booking_confirmation_sms", **_SMS_TASK_RETRY)
def send_booking_confirmation_sms(self, job_id: str) -> dict[str, Any]:
    """Send the customer an SMS after a dispatch job is booked."""
    logger.info(
        "Task starting: send_booking_confirmation_sms attempt=%s",
        self.request.retries + 1,
    )
    session = get_sync_session()
    try:
        job = session.get(DispatchJob, uuid.UUID(job_id))
        if job is None:
            logger.warning("send_booking_confirmation_sms: job %s not found", job_id)
            return {"status": "error", "reason": "job_not_found"}

        customer = session.get(Customer, job.customer_id)
        if customer is None:
            logger.warning(
                "send_booking_confirmation_sms: customer missing for job %s", job_id
            )
            return {"status": "error", "reason": "customer_not_found"}

        if not customer.phone_primary:
            logger.warning(
                "send_booking_confirmation_sms: no phone for customer on job %s",
                job_id,
            )
            return {"status": "error", "reason": "missing_phone"}

        technician_name = "our technician"
        if job.technician_id is not None:
            tech = session.get(Technician, job.technician_id)
            if tech is not None:
                technician_name = tech.full_name

        sent = SmsService().send_booking_confirmation(
            job,
            customer,
            technician_name=technician_name,
        )
        if sent:
            logger.info("Booking confirmation SMS sent for job %s", job_id)
            return {"status": "ok", "job_id": job_id}
        logger.warning("Booking confirmation SMS not sent for job %s", job_id)
        return {"status": "skipped", "job_id": job_id}
    except Exception:
        logger.exception("send_booking_confirmation_sms failed for job %s", job_id)
        raise
    finally:
        session.close()


def _hours_until_appointment(window_start: datetime, now: datetime) -> float:
    start = window_start
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)
    return (start - now).total_seconds() / 3600


def _minutes_until_appointment(window_start: datetime, now: datetime) -> float:
    return _hours_until_appointment(window_start, now) * 60


@celery_app.task(name="app.pipeline.tasks.send_appointment_reminder_24h", **_STANDARD_TASK_RETRY)
def send_appointment_reminder_24h(self, job_id: str) -> dict[str, Any]:
    """Send an SMS reminder 24 hours before the appointment window."""
    logger.info(
        "Task starting: send_appointment_reminder_24h attempt=%s job=%s",
        self.request.retries + 1,
        job_id,
    )
    session = get_sync_session()
    try:
        job = session.get(DispatchJob, uuid.UUID(job_id))
        if job is None:
            logger.warning("send_appointment_reminder_24h: job %s not found", job_id)
            return {"status": "error", "reason": "job_not_found"}

        if job.scheduled_window_start is None:
            logger.warning(
                "send_appointment_reminder_24h: job %s has no scheduled_window_start",
                job_id,
            )
            return {"status": "error", "reason": "missing_window"}

        now = datetime.now(timezone.utc)
        hours_until = _hours_until_appointment(job.scheduled_window_start, now)
        if hours_until > 26 or hours_until < 22:
            logger.warning(
                "send_appointment_reminder_24h: job %s outside 22–26h window (%.2fh)",
                job_id,
                hours_until,
            )
            return {"status": "skipped", "reason": "outside_window", "job_id": job_id}

        customer = session.get(Customer, job.customer_id)
        if customer is None:
            logger.warning(
                "send_appointment_reminder_24h: customer missing for job %s", job_id
            )
            return {"status": "error", "reason": "customer_not_found"}

        if not customer.phone_primary:
            logger.warning(
                "send_appointment_reminder_24h: no phone for customer on job %s",
                job_id,
            )
            return {"status": "error", "reason": "missing_phone"}

        technician_name = "our technician"
        if job.technician_id is not None:
            tech = session.get(Technician, job.technician_id)
            if tech is not None:
                technician_name = tech.full_name

        sent = SmsService().send_24h_reminder(
            job,
            customer,
            technician_name=technician_name,
        )
        if not sent:
            logger.warning("24h appointment reminder SMS not sent for job %s", job_id)
            return {"status": "skipped", "job_id": job_id}

        job.reminder_24h_sent_at = now
        session.commit()
        logger.info("24h appointment reminder SMS sent for job %s", job_id)
        return {"status": "ok", "job_id": job_id}
    except Exception:
        session.rollback()
        logger.exception("send_appointment_reminder_24h failed for job %s", job_id)
        raise
    finally:
        session.close()


@celery_app.task(name="app.pipeline.tasks.send_appointment_reminder_1h", **_STANDARD_TASK_RETRY)
def send_appointment_reminder_1h(self, job_id: str) -> dict[str, Any]:
    """Send an SMS reminder 1 hour before the appointment window."""
    logger.info(
        "Task starting: send_appointment_reminder_1h attempt=%s job=%s",
        self.request.retries + 1,
        job_id,
    )
    session = get_sync_session()
    try:
        job = session.get(DispatchJob, uuid.UUID(job_id))
        if job is None:
            logger.warning("send_appointment_reminder_1h: job %s not found", job_id)
            return {"status": "error", "reason": "job_not_found"}

        if job.scheduled_window_start is None:
            logger.warning(
                "send_appointment_reminder_1h: job %s has no scheduled_window_start",
                job_id,
            )
            return {"status": "error", "reason": "missing_window"}

        now = datetime.now(timezone.utc)
        minutes_until = _minutes_until_appointment(job.scheduled_window_start, now)
        if minutes_until > 90 or minutes_until < 30:
            logger.warning(
                "send_appointment_reminder_1h: job %s outside 30–90m window (%.1fm)",
                job_id,
                minutes_until,
            )
            return {"status": "skipped", "reason": "outside_window", "job_id": job_id}

        customer = session.get(Customer, job.customer_id)
        if customer is None:
            logger.warning(
                "send_appointment_reminder_1h: customer missing for job %s", job_id
            )
            return {"status": "error", "reason": "customer_not_found"}

        if not customer.phone_primary:
            logger.warning(
                "send_appointment_reminder_1h: no phone for customer on job %s",
                job_id,
            )
            return {"status": "error", "reason": "missing_phone"}

        technician_name = "our technician"
        if job.technician_id is not None:
            tech = session.get(Technician, job.technician_id)
            if tech is not None:
                technician_name = tech.full_name

        sent = SmsService().send_1h_reminder(
            job,
            customer,
            technician_name=technician_name,
        )
        if not sent:
            logger.warning("1h appointment reminder SMS not sent for job %s", job_id)
            return {"status": "skipped", "job_id": job_id}

        job.reminder_1h_sent_at = now
        session.commit()
        logger.info("1h appointment reminder SMS sent for job %s", job_id)
        return {"status": "ok", "job_id": job_id}
    except Exception:
        session.rollback()
        logger.exception("send_appointment_reminder_1h failed for job %s", job_id)
        raise
    finally:
        session.close()


@celery_app.task(name="app.pipeline.tasks.sync_google_drive_folders", **_STANDARD_TASK_RETRY)
def sync_google_drive_folders(self) -> dict[str, Any]:
    """Sync Google Drive knowledge folders for connected orgs (Phase 9)."""
    logger.info(
        "Task starting: sync_google_drive_folders attempt=%s",
        self.request.retries + 1,
    )
    return asyncio.run(_sync_google_drive_folders_async())


async def _sync_google_drive_folders_async() -> dict[str, Any]:
    from app.core.database import get_session_factory
    from app.models.organization import Organization
    from app.services.google_drive_service import GoogleDriveService

    summaries: list[str] = []
    total_synced = 0

    async with get_session_factory()() as session:
        try:
            tokens = (
                await session.execute(
                    select(GoogleCalendarToken).where(
                        GoogleCalendarToken.is_active.is_(True)
                    )
                )
            ).scalars().all()

            drive = GoogleDriveService(session)
            seen_orgs: set[uuid.UUID] = set()

            for token in tokens:
                if token.org_id in seen_orgs:
                    continue
                seen_orgs.add(token.org_id)

                org = await session.get(Organization, token.org_id)
                if org is None:
                    continue
                settings = dict(org.settings or {})
                if not settings.get("drive_folder_id"):
                    continue

                try:
                    result = await drive.sync_folder_to_knowledge_base(token.org_id)
                    synced = int(result.get("synced", 0))
                    total_synced += synced
                    name = org.org_name
                    summary = (
                        f"Drive sync: {name} — synced:{synced} "
                        f"skipped:{result.get('skipped', 0)} "
                        f"errors:{result.get('errors', 0)}"
                    )
                    summaries.append(summary)
                    logger.info(summary)
                except Exception as exc:
                    logger.warning(
                        "Drive sync failed for org=%s: %s", token.org_id, exc
                    )

            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {
        "status": "ok",
        "files_synced": total_synced,
        "summaries": summaries,
    }


def _transcript_is_escalated(transcript: CallTranscript) -> bool:
    if transcript.escalation_detected:
        return True
    for field in (transcript.call_summary, transcript.transcript_raw):
        if field and "escalat" in field.lower():
            return True
    if transcript.call_outcome and "escalat" in transcript.call_outcome.lower():
        return True
    return False


def _compute_weekly_stats(
    session,
    org_id: uuid.UUID,
    week_start: datetime,
    week_end: datetime,
) -> dict[str, Any]:
    from calendar import day_name
    from collections import Counter

    transcripts = session.scalars(
        select(CallTranscript).where(
            CallTranscript.org_id == org_id,
            CallTranscript.call_start_utc >= week_start,
            CallTranscript.call_start_utc < week_end,
        )
    ).all()

    total_calls = len(transcripts)
    calls_booked = sum(1 for t in transcripts if t.dispatch_job_id is not None)
    calls_escalated = sum(1 for t in transcripts if _transcript_is_escalated(t))

    new_customers = (
        session.scalar(
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.org_id == org_id,
                Customer.created_at >= week_start,
                Customer.created_at < week_end,
            )
        )
        or 0
    )

    churn_risk_high = (
        session.scalar(
            select(func.count())
            .select_from(Customer)
            .where(
                Customer.org_id == org_id,
                or_(
                    func.upper(Customer.metadata_["churn_tier"].astext).in_(
                        ["HIGH", "CRITICAL"]
                    ),
                    func.lower(Customer.metadata_["churn_risk"].astext).in_(
                        ["high", "critical"]
                    ),
                ),
            )
        )
        or 0
    )

    day_counts = Counter(t.call_start_utc.weekday() for t in transcripts)
    if day_counts:
        busiest_day = day_name[day_counts.most_common(1)[0][0]]
    else:
        busiest_day = "N/A"

    issue_types = session.scalars(
        select(DispatchJob.issue_type).where(
            DispatchJob.org_id == org_id,
            DispatchJob.created_at >= week_start,
            DispatchJob.created_at < week_end,
        )
    ).all()
    issue_counts = Counter(issue for issue in issue_types if issue)
    top_issue_type = issue_counts.most_common(1)[0][0] if issue_counts else "N/A"

    return {
        "total_calls": total_calls,
        "calls_booked": calls_booked,
        "calls_escalated": calls_escalated,
        "new_customers": int(new_customers),
        "churn_risk_high": int(churn_risk_high),
        "busiest_day": busiest_day,
        "top_issue_type": top_issue_type.replace("_", " ").title()
        if top_issue_type != "N/A"
        else top_issue_type,
    }


@celery_app.task(name="app.pipeline.tasks.send_weekly_client_reports", **_STANDARD_TASK_RETRY)
def send_weekly_client_reports(self) -> dict[str, Any]:
    """Email each active org a weekly summary of AI receptionist activity."""
    logger.info(
        "Task starting: send_weekly_client_reports attempt=%s",
        self.request.retries + 1,
    )
    session = get_sync_session()
    sent = 0
    failed = 0
    skipped = 0
    try:
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)

        orgs = session.scalars(
            select(Organization).where(
                Organization.is_active.is_(True),
                text("settings->>'notification_email' IS NOT NULL"),
                text("settings->>'notification_email' != ''"),
            )
        ).all()

        for org in orgs:
            notification_email = str(
                (org.settings or {}).get("notification_email", "")
            ).strip()
            if not notification_email:
                skipped += 1
                continue

            try:
                stats = _compute_weekly_stats(session, org.org_id, week_start, now)
                html_body, text_body = build_weekly_report_html(org.org_name, stats)
                subject = f"Weekly AI Receptionist Report — {org.org_name}"
                if send_email(notification_email, subject, html_body, text_body):
                    sent += 1
                    logger.info(
                        "Weekly report sent to %s for org %s",
                        notification_email,
                        org.org_name,
                    )
                else:
                    failed += 1
                    logger.warning(
                        "Weekly report not sent for org %s (%s)",
                        org.org_name,
                        notification_email,
                    )
            except Exception:
                failed += 1
                logger.exception("Weekly report failed for org %s", org.org_id)

        return {
            "status": "ok",
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "orgs_processed": len(orgs),
        }
    except Exception as exc:
        session.rollback()
        logger.exception("send_weekly_client_reports failed: %s", exc)
        raise
    finally:
        session.close()
