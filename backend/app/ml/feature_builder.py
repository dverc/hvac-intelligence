from __future__ import annotations

import logging
import statistics
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.ml.churn_schema import CHURN_FEATURE_SCHEMA, FEATURE_ORDER
from app.models.call_transcript import CallTranscript
from app.models.churn_score import ChurnScore
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.equipment import Equipment
from app.models.support_ticket import SupportTicket

logger = logging.getLogger(__name__)


class FeatureBuilder:
    """
    Aggregates raw operational data into the 34-feature CHURN_FEATURE_SCHEMA dict.
    Queries call_transcripts, dispatch_jobs, support_tickets, and churn_scores
    for a rolling window (default 90 days).
    """

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def build(
        self,
        entity_id: uuid.UUID | str,
        entity_type: str = "CUSTOMER",
        window_days: int | None = None,
    ) -> dict[str, Any]:
        window_days = window_days or self.settings.FEATURE_WINDOW_DAYS
        entity_uuid = uuid.UUID(str(entity_id))
        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(days=window_days)

        if entity_type != "CUSTOMER":
            logger.warning("Entity type %s not fully supported; returning zeroed features", entity_type)
            base = self._zeroed_features()
        else:
            base = self._build_customer_features(entity_uuid, window_start, window_end)

        base = self._apply_derived_features(base)
        base["_meta"] = {
            "entity_type": entity_type,
            "entity_id": str(entity_uuid),
            "window_start": window_start,
            "window_end": window_end,
            "window_days": window_days,
        }
        return base

    def _build_customer_features(
        self,
        customer_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, Any]:
        customer = self.session.get(Customer, customer_id)
        if customer is None:
            return self._zeroed_features()

        transcripts = self._load_transcripts(customer_id, window_start, window_end)
        jobs = self._load_jobs(customer_id, window_start, window_end)
        tickets = self._load_tickets(customer_id, window_start, window_end)
        self._load_churn_scores(customer_id, window_start, window_end)

        sentiments = [
            float(t.sentiment_overall)
            for t in transcripts
            if t.sentiment_overall is not None
        ]
        slopes = self._per_call_slopes(transcripts)
        anger_scores: list[float] = []
        hesitation_rates: list[float] = []
        recurrence_count = 0
        escalation_count = 0

        for transcript in transcripts:
            if transcript.escalation_detected:
                escalation_count += 1
            emotions = transcript.emotion_labels or {}
            anger_scores.append(float(emotions.get("anger", 0.0)))
            hesitation = transcript.hesitation_markers or {}
            duration = max(int(transcript.duration_seconds or 0), 1)
            markers = int(hesitation.get("pause_count", 0)) + int(
                hesitation.get("filler_word_count", 0)
            )
            hesitation_rates.append(markers / duration)
            meta = transcript.vapi_metadata or {}
            if meta.get("recurrence_complaint_detected"):
                recurrence_count += 1

        total_calls = len(transcripts)
        negative_calls = sum(1 for s in sentiments if s < -0.1)

        features: dict[str, Any] = {
            "escalation_frequency": escalation_count / total_calls if total_calls else 0.0,
            "escalation_count": escalation_count,
            "sentiment_degradation_slope": float(statistics.mean(slopes)) if slopes else 0.0,
            "avg_sentiment_score": float(statistics.mean(sentiments)) if sentiments else 0.0,
            "min_sentiment_score": float(min(sentiments)) if sentiments else 0.0,
            "negative_call_ratio": negative_calls / total_calls if total_calls else 0.0,
            "anger_emotion_ratio": float(statistics.mean(anger_scores)) if anger_scores else 0.0,
            "recurrence_complaint_count": recurrence_count,
            "hesitation_marker_rate": float(statistics.mean(hesitation_rates))
            if hesitation_rates
            else 0.0,
            "sentiment_std_dev": float(statistics.pstdev(sentiments)) if len(sentiments) > 1 else 0.0,
            "sentiment_first_call": sentiments[0] if sentiments else 0.0,
            "sentiment_last_call": sentiments[-1] if sentiments else 0.0,
            "total_calls_window": total_calls,
            **self._operational_features(jobs, tickets),
            **self._account_features(customer, transcripts, jobs),
        }
        return features

    def _operational_features(
        self,
        jobs: list[DispatchJob],
        tickets: list[SupportTicket],
    ) -> dict[str, Any]:
        resolution_hours: list[float] = []
        cancellations = 0
        reschedules = 0
        p1_p2 = 0
        recurrence_jobs = 0
        tech_ids: list[Optional[uuid.UUID]] = []

        issue_counts: dict[str, int] = {}
        for job in jobs:
            tech_ids.append(job.technician_id)
            if job.job_status == "CANCELLED":
                cancellations += 1
            if job.job_status == "RESCHEDULED":
                reschedules += 1
            if job.priority in ("P1", "P2"):
                p1_p2 += 1
            issue_counts[job.issue_type] = issue_counts.get(job.issue_type, 0) + 1
            if job.actual_completion and job.created_at:
                delta = job.actual_completion - job.created_at
                resolution_hours.append(delta.total_seconds() / 3600.0)

        recurrence_jobs = sum(1 for count in issue_counts.values() if count > 1)
        tech_changes = len({t for t in tech_ids if t}) - 1 if tech_ids else 0
        tech_changes = max(tech_changes, 0)

        open_tickets = [t for t in tickets if t.status in ("OPEN", "IN_PROGRESS")]
        now = datetime.now(timezone.utc)
        open_ages = [
            (now - (t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=timezone.utc))).days
            for t in open_tickets
        ]

        job_total = len(jobs) or 1
        return {
            "avg_time_to_resolution_hours": float(statistics.mean(resolution_hours))
            if resolution_hours
            else 0.0,
            "time_to_resolution_std_dev": float(statistics.pstdev(resolution_hours))
            if len(resolution_hours) > 1
            else 0.0,
            "dispatch_cancellation_rate": cancellations / job_total,
            "rescheduling_count": reschedules,
            "open_ticket_age_days_avg": float(statistics.mean(open_ages)) if open_ages else 0.0,
            "open_ticket_count": len(open_tickets),
            "p1_p2_job_count": p1_p2,
            "same_issue_recurrence_count": recurrence_jobs,
            "technician_change_count": tech_changes,
        }

    def _account_features(
        self,
        customer: Customer,
        transcripts: list[CallTranscript],
        jobs: list[DispatchJob],
    ) -> dict[str, Any]:
        meta = customer.metadata_ or {}
        payment_delay = float(meta.get("payment_delay_days_avg", 0) or 0)
        payment_failures = int(meta.get("payment_failure_count", 0) or 0)

        ratings = [
            float(j.customer_rating)
            for j in jobs
            if j.customer_rating is not None
        ]
        rating_meta = meta.get("customer_rating_avg_90d")
        if rating_meta is not None:
            ratings.append(float(rating_meta))

        equipment = self.session.scalars(
            select(Equipment).where(Equipment.customer_id == customer.customer_id)
        ).all()
        equipment_age, warranty_expired = self._equipment_signals(equipment)

        now = datetime.now(timezone.utc)
        positive_days = 365
        for transcript in reversed(transcripts):
            if transcript.sentiment_overall is not None and float(transcript.sentiment_overall) > 0.2:
                start = transcript.call_start_utc
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                positive_days = (now - start).days
                break

        last_service_days = int(meta.get("days_since_last_service", 730) or 730)
        if equipment:
            service_dates = [e.last_service_date for e in equipment if e.last_service_date]
            if service_dates:
                latest = max(service_dates)
                last_service_days = (date.today() - latest).days

        contract_days = int(meta.get("contract_days_until_renewal", 0) or 0)
        renewal = meta.get("contract_renewal_date")
        if renewal:
            try:
                renewal_date = date.fromisoformat(str(renewal)[:10])
                contract_days = (renewal_date - date.today()).days
            except ValueError:
                pass

        return {
            "payment_delay_days_avg": payment_delay,
            "payment_failure_count": payment_failures,
            "days_since_last_positive_call": positive_days,
            "days_since_last_service": last_service_days,
            "contract_days_until_renewal": contract_days,
            "equipment_age_years": equipment_age,
            "warranty_expired": warranty_expired,
            "customer_rating_avg_90d": float(statistics.mean(ratings)) if ratings else 3.0,
        }

    @staticmethod
    def _equipment_signals(equipment: list[Equipment]) -> tuple[float, bool]:
        if not equipment:
            return 0.0, False
        ages: list[float] = []
        warranty_expired = False
        today = date.today()
        for unit in equipment:
            if unit.install_date:
                ages.append((today - unit.install_date).days / 365.25)
            elif unit.age_years is not None:
                ages.append(float(unit.age_years))
            if unit.warranty_expiry and unit.warranty_expiry < today:
                warranty_expired = True
        return (float(max(ages)) if ages else 0.0, warranty_expired)

    @staticmethod
    def _per_call_slopes(transcripts: list[CallTranscript]) -> list[float]:
        slopes: list[float] = []
        for transcript in transcripts:
            trajectory = transcript.sentiment_trajectory or []
            scores = [float(point.get("score", 0.0)) for point in trajectory]
            if len(scores) >= 2:
                import numpy as np

                x = np.arange(len(scores))
                slope, _ = np.polyfit(x, np.array(scores, dtype=float), 1)
                slopes.append(float(slope))
        return slopes

    @staticmethod
    def _apply_derived_features(features: dict[str, Any]) -> dict[str, Any]:
        avg_sent = float(features.get("avg_sentiment_score", 0.0))
        esc_freq = float(features.get("escalation_frequency", 0.0))
        min_sent = float(features.get("min_sentiment_score", 0.0))
        neg_ratio = float(features.get("negative_call_ratio", 0.0))
        slope = float(features.get("sentiment_degradation_slope", 0.0))

        features["sentiment_x_escalation"] = avg_sent * esc_freq
        features["resolution_x_recurrence"] = float(
            features.get("avg_time_to_resolution_hours", 0.0)
        ) * float(features.get("same_issue_recurrence_count", 0))
        features["payment_x_sentiment"] = float(features.get("payment_failure_count", 0)) * (
            1.0 + abs(min_sent)
        )
        features["composite_risk_index"] = (
            neg_ratio * 0.3 + esc_freq * 0.4 + slope * -0.3
        )
        return features

    def _load_transcripts(
        self,
        customer_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CallTranscript]:
        stmt: Select[tuple[CallTranscript]] = (
            select(CallTranscript)
            .where(
                CallTranscript.customer_id == customer_id,
                CallTranscript.call_start_utc >= window_start,
                CallTranscript.call_start_utc <= window_end,
            )
            .order_by(CallTranscript.call_start_utc.asc())
        )
        return list(self.session.scalars(stmt).all())

    def _load_jobs(
        self,
        customer_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> list[DispatchJob]:
        stmt = select(DispatchJob).where(
            DispatchJob.customer_id == customer_id,
            DispatchJob.created_at >= window_start,
            DispatchJob.created_at <= window_end,
        )
        return list(self.session.scalars(stmt).all())

    def _load_tickets(
        self,
        customer_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> list[SupportTicket]:
        stmt = select(SupportTicket).where(
            SupportTicket.customer_id == customer_id,
            SupportTicket.created_at >= window_start,
            SupportTicket.created_at <= window_end,
        )
        return list(self.session.scalars(stmt).all())

    def _load_churn_scores(
        self,
        customer_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ChurnScore]:
        """Loaded for pipeline observability; features derive from operational tables."""
        stmt = select(ChurnScore).where(
            ChurnScore.entity_type == "CUSTOMER",
            ChurnScore.entity_id == customer_id,
            ChurnScore.score_timestamp >= window_start,
            ChurnScore.score_timestamp <= window_end,
        )
        rows = list(self.session.scalars(stmt).all())
        if rows:
            logger.debug(
                "Found %s prior churn_scores for customer %s in window",
                len(rows),
                customer_id,
            )
        return rows

    @staticmethod
    def _zeroed_features() -> dict[str, Any]:
        return {key: 0.0 if spec.get("dtype") != "bool" else False for key, spec in CHURN_FEATURE_SCHEMA.items()}

    @staticmethod
    def model_feature_dict(full_features: dict[str, Any]) -> dict[str, Any]:
        """Strip metadata keys; return only CHURN_FEATURE_SCHEMA fields."""
        return {key: full_features[key] for key in FEATURE_ORDER if key in full_features}
