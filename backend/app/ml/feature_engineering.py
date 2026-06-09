"""Production churn feature engineering — async-first with sync adapter for Celery."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.call_transcript import CallTranscript
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.equipment import Equipment
from app.models.support_ticket import SupportTicket

ML_FEATURE_ORDER: list[str] = [
    "days_since_last_call",
    "days_since_last_service",
    "call_frequency_30d",
    "call_frequency_90d",
    "service_frequency_90d",
    "total_calls_lifetime",
    "contract_value_usd",
    "avg_sentiment_score",
    "sentiment_trend",
    "escalation_count_90d",
    "escalation_frequency",
    "tenure_days",
    "is_annual_contract",
    "is_monthly_contract",
    "payment_method_credit",
    "equipment_count",
    "has_old_equipment",
]

_DEFAULT_FEATURES: dict[str, float] = {
    "days_since_last_call": 365.0,
    "days_since_last_service": 730.0,
    "call_frequency_30d": 0.0,
    "call_frequency_90d": 0.0,
    "service_frequency_90d": 0.0,
    "total_calls_lifetime": 0.0,
    "contract_value_usd": 0.0,
    "avg_sentiment_score": 0.5,
    "sentiment_trend": 0.0,
    "escalation_count_90d": 0.0,
    "escalation_frequency": 0.0,
    "tenure_days": 0.0,
    "is_annual_contract": 0.0,
    "is_monthly_contract": 0.0,
    "payment_method_credit": 0.0,
    "equipment_count": 0.0,
    "has_old_equipment": 0.0,
}

_OLD_EQUIPMENT_YEARS = 7


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_sentiment(raw: float | Decimal | None) -> float:
    """Map [-1, 1] compound sentiment to [0, 1] probability-friendly scale."""
    if raw is None:
        return 0.5
    score = float(raw)
    return max(0.0, min(1.0, (score + 1.0) / 2.0))


def _days_since(dt: datetime | date | None, today: datetime) -> float:
    if dt is None:
        return _DEFAULT_FEATURES["days_since_last_call"]
    if isinstance(dt, datetime):
        dt = _as_utc(dt).date()
    return float(max((today.date() - dt).days, 0))


def _compute_features(
    customer: Customer,
    transcripts: list[CallTranscript],
    jobs: list[DispatchJob],
    tickets: list[SupportTicket],
    equipment: list[Equipment],
    *,
    now: datetime | None = None,
) -> dict[str, float]:
    now = now or _utc_now()
    today = now
    cutoff_30 = now - timedelta(days=30)
    cutoff_90 = now - timedelta(days=90)

    transcripts_sorted = sorted(
        transcripts,
        key=lambda t: _as_utc(t.call_start_utc),
    )

    if transcripts_sorted:
        last_call = _as_utc(transcripts_sorted[-1].call_start_utc)
        days_since_last_call = float(max((today - last_call).days, 0))
    else:
        days_since_last_call = _DEFAULT_FEATURES["days_since_last_call"]

    completed_jobs = [
        j
        for j in jobs
        if j.job_status == "COMPLETED"
    ]
    completion_dates: list[datetime] = []
    for job in completed_jobs:
        if job.actual_completion is not None:
            completion_dates.append(_as_utc(job.actual_completion))
        elif job.scheduled_window_end is not None:
            completion_dates.append(_as_utc(job.scheduled_window_end))

    if completion_dates:
        last_service = max(completion_dates)
        days_since_last_service = float(max((today - last_service).days, 0))
    else:
        days_since_last_service = _DEFAULT_FEATURES["days_since_last_service"]

    call_frequency_30d = float(
        sum(1 for t in transcripts if _as_utc(t.call_start_utc) >= cutoff_30)
    )
    call_frequency_90d = float(
        sum(1 for t in transcripts if _as_utc(t.call_start_utc) >= cutoff_90)
    )
    service_frequency_90d = float(
        sum(
            1
            for j in completed_jobs
            if j.actual_completion is not None
            and _as_utc(j.actual_completion) >= cutoff_90
        )
    )
    total_calls_lifetime = float(len(transcripts))

    contract_value = customer.contract_value_usd
    contract_value_usd = float(contract_value) if contract_value is not None else 0.0

    normalized_sentiments = [
        _normalize_sentiment(t.sentiment_overall) for t in transcripts_sorted
    ]
    avg_sentiment_score = (
        float(sum(normalized_sentiments) / len(normalized_sentiments))
        if normalized_sentiments
        else _DEFAULT_FEATURES["avg_sentiment_score"]
    )

    sentiment_trend = 0.0
    if len(normalized_sentiments) >= 3:
        sentiment_trend = normalized_sentiments[-1] - normalized_sentiments[-3]

    escalation_count_90d = float(
        sum(
            1
            for ticket in tickets
            if ticket.priority in ("P1", "P2")
            and ticket.created_at is not None
            and _as_utc(ticket.created_at) >= cutoff_90
        )
    )
    escalation_frequency = escalation_count_90d / max(call_frequency_90d, 1.0)

    tenure_days = float(max((today.date() - customer.customer_since).days, 0))

    contract_type = (customer.contract_type or "").upper()
    is_annual_contract = 1.0 if "ANNUAL" in contract_type else 0.0
    is_monthly_contract = 1.0 if "MONTHLY" in contract_type else 0.0

    payment_method = (customer.payment_method or "").upper()
    payment_method_credit = 1.0 if payment_method == "CREDIT_CARD" else 0.0

    equipment_count = float(len(equipment))
    has_old_equipment = 0.0
    for unit in equipment:
        if unit.install_date is not None:
            age_years = (date.today() - unit.install_date).days / 365.25
            if age_years > _OLD_EQUIPMENT_YEARS:
                has_old_equipment = 1.0
                break
        elif unit.age_years is not None and float(unit.age_years) > _OLD_EQUIPMENT_YEARS:
            has_old_equipment = 1.0
            break

    features = {
        "days_since_last_call": days_since_last_call,
        "days_since_last_service": days_since_last_service,
        "call_frequency_30d": call_frequency_30d,
        "call_frequency_90d": call_frequency_90d,
        "service_frequency_90d": service_frequency_90d,
        "total_calls_lifetime": total_calls_lifetime,
        "contract_value_usd": contract_value_usd,
        "avg_sentiment_score": avg_sentiment_score,
        "sentiment_trend": sentiment_trend,
        "escalation_count_90d": escalation_count_90d,
        "escalation_frequency": escalation_frequency,
        "tenure_days": tenure_days,
        "is_annual_contract": is_annual_contract,
        "is_monthly_contract": is_monthly_contract,
        "payment_method_credit": payment_method_credit,
        "equipment_count": equipment_count,
        "has_old_equipment": has_old_equipment,
    }
    return {key: float(features.get(key, _DEFAULT_FEATURES[key])) for key in ML_FEATURE_ORDER}


async def build_customer_features(
    customer_id: uuid.UUID | str,
    db: AsyncSession,
) -> dict[str, float]:
    """Build churn ML features for a customer (async SQLAlchemy session)."""
    cid = uuid.UUID(str(customer_id))
    customer = await db.get(Customer, cid)
    if customer is None:
        return dict(_DEFAULT_FEATURES)

    transcripts = list(
        (
            await db.execute(
                select(CallTranscript)
                .where(CallTranscript.customer_id == cid)
                .order_by(CallTranscript.call_start_utc.asc())
            )
        ).scalars()
    )
    jobs = list(
        (
            await db.execute(
                select(DispatchJob).where(DispatchJob.customer_id == cid)
            )
        ).scalars()
    )
    tickets = list(
        (
            await db.execute(
                select(SupportTicket).where(SupportTicket.customer_id == cid)
            )
        ).scalars()
    )
    equipment = list(
        (
            await db.execute(
                select(Equipment).where(Equipment.customer_id == cid)
            )
        ).scalars()
    )
    return _compute_features(customer, transcripts, jobs, tickets, equipment)


def build_customer_features_sync(
    customer_id: uuid.UUID | str,
    session: Session,
) -> dict[str, float]:
    """Sync variant for Celery workers."""
    cid = uuid.UUID(str(customer_id))
    customer = session.get(Customer, cid)
    if customer is None:
        return dict(_DEFAULT_FEATURES)

    transcripts = list(
        session.scalars(
            select(CallTranscript)
            .where(CallTranscript.customer_id == cid)
            .order_by(CallTranscript.call_start_utc.asc())
        ).all()
    )
    jobs = list(
        session.scalars(
            select(DispatchJob).where(DispatchJob.customer_id == cid)
        ).all()
    )
    tickets = list(
        session.scalars(
            select(SupportTicket).where(SupportTicket.customer_id == cid)
        ).all()
    )
    equipment = list(
        session.scalars(
            select(Equipment).where(Equipment.customer_id == cid)
        ).all()
    )
    return _compute_features(customer, transcripts, jobs, tickets, equipment)
