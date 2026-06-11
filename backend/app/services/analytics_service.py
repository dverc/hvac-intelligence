from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, time, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_transcript import CallTranscript
from app.models.churn_score import ChurnScore
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.support_ticket import SupportTicket
from app.schemas.analytics import (
    CallAnalyticsResponse,
    CallAnalyticsSummary,
    CallsByDayItem,
    CallsByHourItem,
    ChurnDistributionResponse,
    ChurnTimelinePoint,
    ChurnTimelineResponse,
    CohortBucket,
    CohortBucketSample,
    CohortHeatmapBucket,
    CohortHeatmapResponse,
    FeatureImportanceItem,
    FeatureImportanceResponse,
    MonthlyTrendPoint,
    RetentionEventItem,
    RetentionEventsResponse,
    RevenueImpact,
    SavedByAIResponse,
    SentimentBreakdown,
    TimelineEvent,
    TopInterventionType,
    TopIssueTypeItem,
    WeekOverWeekDelta,
)
from app.core.metrics import high_risk_accounts_gauge
from app.core.tenant import scoped
from app.services.churn_service import TIER_DEFAULT_PROBABILITY

RISK_TIERS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


class AnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_churn_probability_distribution(
        self, org_id: uuid.UUID
    ) -> ChurnDistributionResponse:
        as_of = datetime.now(timezone.utc)
        snapshots = await self._latest_customer_snapshots(org_id, as_of)
        total = len(snapshots)

        cohort_stats: dict[str, dict[str, Any]] = {
            tier: {"count": 0, "score_sum": 0.0, "arr_sum": 0.0}
            for tier in RISK_TIERS
        }
        for snap in snapshots:
            tier = snap["risk_tier"]
            if tier not in cohort_stats:
                tier = "LOW"
            cohort_stats[tier]["count"] += 1
            cohort_stats[tier]["score_sum"] += snap["churn_probability"]
            cohort_stats[tier]["arr_sum"] += snap["contract_value_usd"]

        cohorts: list[CohortBucket] = []
        for tier in RISK_TIERS:
            stats = cohort_stats[tier]
            count = stats["count"]
            avg_score = stats["score_sum"] / count if count else 0.0
            avg_contract = stats["arr_sum"] / count if count else 0.0
            cohorts.append(
                CohortBucket(
                    tier=tier,  # type: ignore[arg-type]
                    count=count,
                    percentage=round((count / total * 100) if total else 0.0, 1),
                    avg_score=round(avg_score, 2),
                    estimated_arr_at_risk_usd=round(count * avg_contract, 2)
                    if tier in ("MEDIUM", "HIGH", "CRITICAL")
                    else 0.0,
                )
            )

        week_ago = as_of - timedelta(days=7)
        prior_snapshots = await self._latest_customer_snapshots(org_id, week_ago)
        prior_total = len(prior_snapshots)
        prior_counts = defaultdict(int)
        for snap in prior_snapshots:
            prior_counts[snap["risk_tier"]] += 1

        week_over_week: list[WeekOverWeekDelta] = []
        for tier in RISK_TIERS:
            current = cohort_stats[tier]["count"]
            prior = prior_counts.get(tier, 0)
            delta_count = current - prior
            current_pct = (current / total * 100) if total else 0.0
            prior_pct = (prior / prior_total * 100) if prior_total else 0.0
            week_over_week.append(
                WeekOverWeekDelta(
                    tier=tier,
                    delta_count=delta_count,
                    delta_percentage=round(current_pct - prior_pct, 1),
                )
            )

        high_risk_count = (
            cohort_stats["HIGH"]["count"] + cohort_stats["CRITICAL"]["count"]
        )
        high_risk_accounts_gauge.set(high_risk_count)

        return ChurnDistributionResponse(
            as_of=as_of.isoformat().replace("+00:00", "Z"),
            total_customers=total,
            cohorts=cohorts,
            week_over_week_delta=week_over_week,
        )

    async def get_saved_by_ai(
        self,
        org_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> SavedByAIResponse:
        if period_start.tzinfo is None:
            period_start = period_start.replace(tzinfo=timezone.utc)
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)

        stmt = select(CallTranscript, Customer).join(
            Customer, CallTranscript.customer_id == Customer.customer_id
        ).where(
            CallTranscript.org_id == org_id,
            Customer.org_id == org_id,
            CallTranscript.call_start_utc >= period_start,
            CallTranscript.call_start_utc <= period_end,
            CallTranscript.churn_risk_at_call_start.isnot(None),
            CallTranscript.churn_risk_at_call_start > Decimal("0.6"),
        )
        rows = (await self.db.execute(stmt)).all()

        reductions: list[float] = []
        successful = 0
        monthly: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"interventions": 0, "arr": 0.0, "successes": 0, "attempts": 0}
        )
        intervention_types: dict[str, list[float]] = defaultdict(list)

        for transcript, customer in rows:
            start_score = float(transcript.churn_risk_at_call_start or 0)
            end_score = (
                float(transcript.churn_risk_at_call_end)
                if transcript.churn_risk_at_call_end is not None
                else start_score
            )
            delta = start_score - end_score
            month_key = transcript.call_start_utc.strftime("%Y-%m")
            monthly[month_key]["attempts"] += 1

            success = bool(transcript.intervention_successful) or delta >= 0.15
            if success:
                successful += 1
                reductions.append(delta)
                monthly[month_key]["interventions"] += 1
                monthly[month_key]["successes"] += 1
                contract = float(customer.contract_value_usd or 0)
                monthly[month_key]["arr"] += contract

            intervention_type = _infer_intervention_type(transcript)
            if success:
                intervention_types[intervention_type].append(delta)

        total_high_risk = len(rows)
        success_rate = (
            round(successful / total_high_risk * 100, 1) if total_high_risk else 0.0
        )
        avg_reduction = (
            round(sum(reductions) / len(reductions), 3) if reductions else 0.0
        )
        arr_retained = sum(monthly[m]["arr"] for m in monthly)

        monthly_trend = [
            MonthlyTrendPoint(
                month=month,
                interventions=data["interventions"],
                arr_retained_usd=round(data["arr"], 2),
                success_rate=round(
                    data["successes"] / data["attempts"] * 100, 1
                )
                if data["attempts"]
                else 0.0,
            )
            for month, data in sorted(monthly.items())
        ]

        top_types = sorted(
            [
                TopInterventionType(
                    type=itype,
                    count=len(deltas),
                    avg_score_reduction=round(sum(deltas) / len(deltas), 3),
                )
                for itype, deltas in intervention_types.items()
                if deltas
            ],
            key=lambda item: item.count,
            reverse=True,
        )[:5]

        return SavedByAIResponse(
            period_start=period_start.isoformat().replace("+00:00", "Z"),
            period_end=period_end.isoformat().replace("+00:00", "Z"),
            total_high_risk_calls=total_high_risk,
            successful_interventions=successful,
            intervention_success_rate=success_rate,
            estimated_arr_retained_usd=round(arr_retained, 2),
            avg_score_reduction=avg_reduction,
            monthly_trend=monthly_trend,
            top_intervention_types=top_types,
        )

    async def get_retention_events(
        self,
        org_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> RetentionEventsResponse:
        if period_start.tzinfo is None:
            period_start = period_start.replace(tzinfo=timezone.utc)
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)

        events: list[RetentionEventItem] = []

        call_rows = (
            await self.db.execute(
                select(CallTranscript, Customer)
                .join(Customer, CallTranscript.customer_id == Customer.customer_id)
                .where(
                    CallTranscript.org_id == org_id,
                    Customer.org_id == org_id,
                    CallTranscript.call_start_utc >= period_start,
                    CallTranscript.call_start_utc <= period_end,
                )
                .order_by(CallTranscript.call_start_utc.desc())
            )
        ).all()

        for transcript, customer in call_rows:
            start_score = (
                float(transcript.churn_risk_at_call_start)
                if transcript.churn_risk_at_call_start is not None
                else None
            )
            end_score = (
                float(transcript.churn_risk_at_call_end)
                if transcript.churn_risk_at_call_end is not None
                else None
            )
            saved = (
                start_score is not None
                and end_score is not None
                and (start_score - end_score) >= 0.15
            )

            if start_score is not None and start_score > 0.6:
                events.append(
                    RetentionEventItem(
                        event_id=str(transcript.transcript_id),
                        timestamp=transcript.call_start_utc.isoformat().replace(
                            "+00:00", "Z"
                        ),
                        event_type="CALL_START",
                        customer_id=str(customer.customer_id),
                        customer_name=customer.full_name,
                        call_id=transcript.call_id,
                        churn_probability_before=start_score,
                        churn_probability_after=end_score,
                        risk_tier=_score_to_tier(start_score),
                        label=_call_start_label(transcript),
                        saved_by_ai=saved,
                    )
                )

            if saved or transcript.intervention_successful:
                events.append(
                    RetentionEventItem(
                        event_id=f"{transcript.transcript_id}-intervention",
                        timestamp=(transcript.call_end_utc or transcript.call_start_utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        event_type="INTERVENTION_APPLIED",
                        customer_id=str(customer.customer_id),
                        customer_name=customer.full_name,
                        call_id=transcript.call_id,
                        churn_probability_before=start_score,
                        churn_probability_after=end_score,
                        risk_tier=_score_to_tier(end_score or start_score or 0.0),
                        label="AI retention intervention — score improved ≥15%",
                        saved_by_ai=True,
                    )
                )

        job_rows = (
            await self.db.execute(
                select(DispatchJob, Customer)
                .join(Customer, DispatchJob.customer_id == Customer.customer_id)
                .where(
                    DispatchJob.org_id == org_id,
                    Customer.org_id == org_id,
                    DispatchJob.created_at >= period_start,
                    DispatchJob.created_at <= period_end,
                    DispatchJob.priority.in_(("P1", "P2")),
                )
                .order_by(DispatchJob.created_at.desc())
            )
        ).all()

        for job, customer in job_rows:
            events.append(
                RetentionEventItem(
                    event_id=str(job.job_id),
                    timestamp=job.created_at.isoformat().replace("+00:00", "Z"),
                    event_type="DISPATCH_CREATED",
                    customer_id=str(customer.customer_id),
                    customer_name=customer.full_name,
                    label=f"{job.priority} dispatch: {job.issue_type} (#{job.job_number})",
                    risk_tier=None,
                    saved_by_ai=False,
                )
            )

        score_rows = (
            await self.db.execute(
                select(ChurnScore, Customer)
                .join(Customer, ChurnScore.entity_id == Customer.customer_id)
                .where(
                    ChurnScore.org_id == org_id,
                    Customer.org_id == org_id,
                    ChurnScore.entity_type == "CUSTOMER",
                    ChurnScore.score_timestamp >= period_start,
                    ChurnScore.score_timestamp <= period_end,
                )
                .order_by(ChurnScore.score_timestamp.desc())
            )
        ).all()

        for score, customer in score_rows:
            events.append(
                RetentionEventItem(
                    event_id=str(score.score_id),
                    timestamp=score.score_timestamp.isoformat().replace("+00:00", "Z"),
                    event_type="SCORE_CHANGE",
                    customer_id=str(customer.customer_id),
                    customer_name=customer.full_name,
                    churn_probability_after=float(score.churn_probability),
                    risk_tier=score.risk_tier,
                    label=f"Churn score updated → {score.risk_tier} ({float(score.churn_probability):.0%})",
                    saved_by_ai=False,
                )
            )

        churned = (
            await self.db.execute(
                scoped(
                    select(Customer).where(
                        Customer.account_status == "CHURNED",
                        Customer.updated_at >= period_start,
                        Customer.updated_at <= period_end,
                    ),
                    Customer,
                    org_id,
                )
            )
        ).scalars().all()

        for customer in churned:
            events.append(
                RetentionEventItem(
                    event_id=f"churned-{customer.customer_id}",
                    timestamp=customer.updated_at.isoformat().replace("+00:00", "Z"),
                    event_type="CHURNED",
                    customer_id=str(customer.customer_id),
                    customer_name=customer.full_name,
                    label="Account marked CHURNED",
                    risk_tier="CRITICAL",
                    saved_by_ai=False,
                )
            )

        events.sort(key=lambda item: item.timestamp, reverse=True)

        return RetentionEventsResponse(
            period_start=period_start.isoformat().replace("+00:00", "Z"),
            period_end=period_end.isoformat().replace("+00:00", "Z"),
            events=events,
        )

    async def get_feature_importance(
        self,
        org_id: uuid.UUID,
        model_version: str = "latest",
    ) -> FeatureImportanceResponse:
        as_of = datetime.now(timezone.utc)

        stmt = scoped(
            select(ChurnScore).where(
                ChurnScore.entity_type == "CUSTOMER",
                ChurnScore.feature_contributions.isnot(None),
            ),
            ChurnScore,
            org_id,
        ).order_by(ChurnScore.score_timestamp.desc()).limit(500)
        if model_version != "latest":
            stmt = stmt.where(ChurnScore.model_version == model_version)

        rows = (await self.db.execute(stmt)).scalars().all()
        if not rows:
            return FeatureImportanceResponse(
                model_version=None,
                as_of=as_of.isoformat().replace("+00:00", "Z"),
                source="no_contributions",
                features=[],
            )

        aggregates: dict[str, dict[str, float]] = defaultdict(
            lambda: {"sum": 0.0, "count": 0.0, "increases": 0.0}
        )
        resolved_version: str | None = None

        for row in rows:
            if resolved_version is None and row.model_version:
                resolved_version = row.model_version
            contributions = row.feature_contributions or []
            for item in contributions:
                if not isinstance(item, dict):
                    continue
                feature = item.get("feature")
                shap = item.get("shap_value")
                if not feature or shap is None:
                    continue
                shap_f = float(shap)
                aggregates[feature]["sum"] += shap_f
                aggregates[feature]["count"] += 1.0
                if shap_f > 0:
                    aggregates[feature]["increases"] += 1.0

        features: list[FeatureImportanceItem] = []
        for feature, stats in aggregates.items():
            count = stats["count"] or 1.0
            avg_shap = stats["sum"] / count
            features.append(
                FeatureImportanceItem(
                    feature=feature,
                    avg_shap_value=round(avg_shap, 4),
                    importance=round(abs(avg_shap), 4),
                    direction="INCREASES_RISK"
                    if stats["increases"] >= count / 2
                    else "DECREASES_RISK",
                )
            )

        features.sort(key=lambda item: item.importance, reverse=True)

        return FeatureImportanceResponse(
            model_version=resolved_version if model_version == "latest" else model_version,
            as_of=as_of.isoformat().replace("+00:00", "Z"),
            source="aggregated_churn_scores",
            features=features[:20],
        )

    async def get_churn_timeline(
        self, org_id: uuid.UUID, customer_id: uuid.UUID
    ) -> ChurnTimelineResponse:
        customer = await self.db.get(Customer, customer_id)
        if customer is None or customer.org_id != org_id:
            raise ValueError("Customer not found")

        since = datetime.now(timezone.utc) - timedelta(days=90)

        scores = (
            await self.db.execute(
                scoped(
                    select(ChurnScore).where(
                        ChurnScore.entity_type == "CUSTOMER",
                        ChurnScore.entity_id == customer_id,
                        ChurnScore.score_timestamp >= since,
                    ),
                    ChurnScore,
                    org_id,
                ).order_by(ChurnScore.score_timestamp.asc())
            )
        ).scalars().all()

        transcripts = (
            await self.db.execute(
                scoped(
                    select(CallTranscript).where(
                        CallTranscript.customer_id == customer_id,
                        CallTranscript.call_start_utc >= since,
                    ),
                    CallTranscript,
                    org_id,
                ).order_by(CallTranscript.call_start_utc.asc())
            )
        ).scalars().all()

        jobs = (
            await self.db.execute(
                scoped(
                    select(DispatchJob).where(
                        DispatchJob.customer_id == customer_id,
                        DispatchJob.created_at >= since,
                    ),
                    DispatchJob,
                    org_id,
                ).order_by(DispatchJob.created_at.asc())
            )
        ).scalars().all()

        tickets = (
            await self.db.execute(
                scoped(
                    select(SupportTicket).where(
                        SupportTicket.customer_id == customer_id,
                        SupportTicket.resolved_at.isnot(None),
                        SupportTicket.resolved_at >= since,
                    ),
                    SupportTicket,
                    org_id,
                )
            )
        ).scalars().all()

        event_index: dict[str, dict[str, Any]] = {}

        for transcript in transcripts:
            ts = transcript.call_start_utc.isoformat().replace("+00:00", "Z")
            event_index[ts] = {
                "type": "CALL_START",
                "label": _call_start_label(transcript),
                "call_id": transcript.call_id,
            }
            if transcript.intervention_successful or (
                transcript.churn_risk_at_call_start is not None
                and transcript.churn_risk_at_call_end is not None
                and float(transcript.churn_risk_at_call_start)
                - float(transcript.churn_risk_at_call_end)
                >= 0.15
            ):
                end_ts = (transcript.call_end_utc or transcript.call_start_utc).isoformat()
                end_ts = end_ts.replace("+00:00", "Z")
                event_index[end_ts] = {
                    "type": "INTERVENTION_APPLIED",
                    "label": _intervention_label(transcript, jobs),
                    "call_id": transcript.call_id,
                }

        for job in jobs:
            ts = job.created_at.isoformat().replace("+00:00", "Z")
            if ts not in event_index:
                event_index[ts] = {
                    "type": "DISPATCH_CREATED",
                    "label": f"{job.priority} dispatch scheduled — {job.issue_type}",
                    "call_id": None,
                }

        for ticket in tickets:
            if ticket.resolved_at is None:
                continue
            ts = ticket.resolved_at.isoformat().replace("+00:00", "Z")
            event_index[ts] = {
                "type": "TICKET_RESOLVED",
                "label": f"Ticket resolved: {ticket.subject[:80]}",
                "call_id": None,
            }

        if customer.account_status == "CHURNED":
            ts = customer.updated_at.isoformat().replace("+00:00", "Z")
            event_index[ts] = {
                "type": "CHURNED",
                "label": "Account churned",
                "call_id": None,
            }

        data_points: list[dict[str, Any]] = []

        if scores:
            for score in scores:
                ts = score.score_timestamp.isoformat().replace("+00:00", "Z")
                point: dict[str, Any] = {
                    "timestamp": ts,
                    "churn_probability": float(score.churn_probability),
                    "risk_tier": score.risk_tier,
                }
                if ts in event_index:
                    point["event"] = event_index[ts]
                data_points.append(point)
        else:
            meta = customer.metadata_ or {}
            tier = str(meta.get("churn_tier", "LOW")).upper()
            prob = float(
                meta.get("churn_probability", TIER_DEFAULT_PROBABILITY.get(tier, 0.2))
            )
            data_points.append(
                {
                    "timestamp": customer.created_at.isoformat().replace("+00:00", "Z"),
                    "churn_probability": prob,
                    "risk_tier": tier,
                }
            )

        for transcript in transcripts:
            if transcript.churn_risk_at_call_end is not None:
                ts = (transcript.call_end_utc or transcript.call_start_utc).isoformat()
                ts = ts.replace("+00:00", "Z")
                if not any(p["timestamp"] == ts for p in data_points):
                    data_points.append(
                        {
                            "timestamp": ts,
                            "churn_probability": float(transcript.churn_risk_at_call_end),
                            "risk_tier": _score_to_tier(
                                float(transcript.churn_risk_at_call_end)
                            ),
                            "event": event_index.get(ts),
                        }
                    )

        data_points.sort(key=lambda point: point["timestamp"])

        if not data_points:
            data_points.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "churn_probability": 0.0,
                    "risk_tier": "LOW",
                }
            )

        current_score = float(data_points[-1]["churn_probability"])
        score_90d_ago = float(data_points[0]["churn_probability"])
        net_change = round(current_score - score_90d_ago, 3)

        interventions_count = sum(
            1
            for transcript in transcripts
            if transcript.intervention_successful
            or (
                transcript.churn_risk_at_call_start is not None
                and transcript.churn_risk_at_call_end is not None
                and float(transcript.churn_risk_at_call_start)
                - float(transcript.churn_risk_at_call_end)
                >= 0.15
            )
        )

        saved_by_ai = net_change <= -0.15 and interventions_count > 0

        timeline_points: list[ChurnTimelinePoint] = []
        for point in data_points:
            raw_event = point.get("event")
            event = TimelineEvent(**raw_event) if raw_event else None
            timeline_points.append(
                ChurnTimelinePoint(
                    timestamp=point["timestamp"],
                    churn_probability=point["churn_probability"],
                    risk_tier=point["risk_tier"],
                    event=event,
                )
            )

        return ChurnTimelineResponse(
            customer_id=str(customer_id),
            customer_name=customer.full_name,
            data_points=timeline_points,
            current_score=current_score,
            score_90d_ago=score_90d_ago,
            net_change=net_change,
            interventions_count=interventions_count,
            saved_by_ai=saved_by_ai,
        )

    async def get_cohort_heatmap(
        self,
        org_id: uuid.UUID,
        window_days: int = 90,
        bucket_count: int = 10,
    ) -> CohortHeatmapResponse:
        """§5.1.3 — score buckets with ARR and intervention success rates."""
        as_of = datetime.now(timezone.utc)
        window_start = as_of - timedelta(days=window_days)
        snapshots = await self._latest_customer_snapshots(org_id, as_of)

        if not snapshots or bucket_count < 1:
            return CohortHeatmapResponse(
                generated_at=as_of.isoformat().replace("+00:00", "Z"),
                buckets=[],
            )

        width = 1.0 / bucket_count
        buckets: list[CohortHeatmapBucket] = []

        for index in range(bucket_count):
            low = round(index * width, 4)
            high = round((index + 1) * width, 4) if index < bucket_count - 1 else 1.0

            if index == bucket_count - 1:
                in_bucket = [
                    snap
                    for snap in snapshots
                    if low <= snap["churn_probability"] <= high
                ]
            else:
                in_bucket = [
                    snap
                    for snap in snapshots
                    if low <= snap["churn_probability"] < high
                ]

            if not in_bucket:
                buckets.append(
                    CohortHeatmapBucket(
                        score_range_low=low,
                        score_range_high=high,
                        customer_count=0,
                        avg_arr_usd=0.0,
                        intervention_success_rate=0.0,
                        top_features=[],
                        customers_sample=[],
                    )
                )
                continue

            customer_ids = [snap["customer_id"] for snap in in_bucket]
            transcripts = (
                await self.db.execute(
                    scoped(
                        select(CallTranscript).where(
                            CallTranscript.customer_id.in_(customer_ids),
                            CallTranscript.call_start_utc >= window_start,
                        ),
                        CallTranscript,
                        org_id,
                    )
                )
            ).scalars().all()

            success_by_customer: dict[uuid.UUID, bool] = defaultdict(bool)
            for transcript in transcripts:
                if transcript.customer_id is None:
                    continue
                if transcript.intervention_successful:
                    success_by_customer[transcript.customer_id] = True
                elif (
                    transcript.churn_risk_at_call_start is not None
                    and transcript.churn_risk_at_call_end is not None
                    and float(transcript.churn_risk_at_call_start)
                    - float(transcript.churn_risk_at_call_end)
                    >= 0.15
                ):
                    success_by_customer[transcript.customer_id] = True

            successes = sum(
                1 for customer_id in customer_ids if success_by_customer.get(customer_id)
            )
            success_rate = (successes / len(customer_ids) * 100) if customer_ids else 0.0

            arr_values = [snap["contract_value_usd"] for snap in in_bucket]
            avg_arr = sum(arr_values) / len(arr_values) if arr_values else 0.0

            feature_counts: dict[str, int] = defaultdict(int)
            score_rows = (
                await self.db.execute(
                    scoped(
                        select(ChurnScore).where(
                            ChurnScore.entity_type == "CUSTOMER",
                            ChurnScore.entity_id.in_(customer_ids),
                            ChurnScore.feature_contributions.isnot(None),
                        ),
                        ChurnScore,
                        org_id,
                    )
                )
            ).scalars().all()
            for row in score_rows:
                for item in row.feature_contributions or []:
                    if isinstance(item, dict) and item.get("feature"):
                        feature_counts[str(item["feature"])] += 1
            top_features = [
                name
                for name, _ in sorted(
                    feature_counts.items(), key=lambda pair: pair[1], reverse=True
                )[:3]
            ]

            customers = (
                await self.db.execute(
                    scoped(
                        select(Customer).where(Customer.customer_id.in_(customer_ids)),
                        Customer,
                        org_id,
                    )
                )
            ).scalars().all()
            name_by_id = {customer.customer_id: customer.full_name for customer in customers}

            sample = sorted(in_bucket, key=lambda s: s["churn_probability"], reverse=True)[:5]
            customers_sample = [
                CohortBucketSample(
                    customer_id=str(snap["customer_id"]),
                    name=name_by_id.get(snap["customer_id"], "Unknown"),
                    score=round(snap["churn_probability"], 3),
                )
                for snap in sample
            ]

            buckets.append(
                CohortHeatmapBucket(
                    score_range_low=low,
                    score_range_high=high,
                    customer_count=len(in_bucket),
                    avg_arr_usd=round(avg_arr, 2),
                    intervention_success_rate=round(success_rate, 1),
                    top_features=top_features,
                    customers_sample=customers_sample,
                )
            )

        return CohortHeatmapResponse(
            generated_at=as_of.isoformat().replace("+00:00", "Z"),
            buckets=buckets,
        )

    async def _latest_customer_snapshots(
        self, org_id: uuid.UUID, as_of: datetime
    ) -> list[dict[str, Any]]:
        """Latest churn score per customer at `as_of`, with metadata fallback."""
        latest_subq = (
            select(
                ChurnScore.entity_id.label("entity_id"),
                func.max(ChurnScore.score_timestamp).label("max_ts"),
            )
            .where(
                ChurnScore.org_id == org_id,
                ChurnScore.entity_type == "CUSTOMER",
                ChurnScore.score_timestamp <= as_of,
            )
            .group_by(ChurnScore.entity_id)
            .subquery()
        )

        score_rows = (
            await self.db.execute(
                select(ChurnScore, Customer)
                .join(
                    latest_subq,
                    and_(
                        ChurnScore.entity_id == latest_subq.c.entity_id,
                        ChurnScore.score_timestamp == latest_subq.c.max_ts,
                    ),
                )
                .join(Customer, ChurnScore.entity_id == Customer.customer_id)
                .where(
                    ChurnScore.org_id == org_id,
                    Customer.org_id == org_id,
                    Customer.account_status.in_(("ACTIVE", "SUSPENDED", "PROSPECT")),
                )
            )
        ).all()

        snapshots: dict[uuid.UUID, dict[str, Any]] = {}
        for score, customer in score_rows:
            snapshots[customer.customer_id] = {
                "customer_id": customer.customer_id,
                "risk_tier": score.risk_tier,
                "churn_probability": float(score.churn_probability),
                "contract_value_usd": float(customer.contract_value_usd or 0),
            }

        customers = (
            await self.db.execute(
                scoped(
                    select(Customer).where(
                        Customer.account_status.in_(("ACTIVE", "SUSPENDED", "PROSPECT"))
                    ),
                    Customer,
                    org_id,
                )
            )
        ).scalars().all()

        for customer in customers:
            if customer.customer_id in snapshots:
                continue
            meta = customer.metadata_ or {}
            tier = str(meta.get("churn_tier", "LOW")).upper()
            prob = float(
                meta.get("churn_probability", TIER_DEFAULT_PROBABILITY.get(tier, 0.2))
            )
            snapshots[customer.customer_id] = {
                "customer_id": customer.customer_id,
                "risk_tier": tier,
                "churn_probability": prob,
                "contract_value_usd": float(customer.contract_value_usd or 0),
            }

        return list(snapshots.values())

    async def get_call_analytics(
        self, org_id: uuid.UUID, days: int
    ) -> CallAnalyticsResponse:
        end = datetime.now(timezone.utc)
        range_start_date = (end - timedelta(days=days - 1)).date()
        range_start = datetime.combine(range_start_date, time.min, tzinfo=timezone.utc)

        transcripts = (
            await self.db.execute(
                scoped(
                    select(CallTranscript).where(
                        CallTranscript.call_start_utc >= range_start,
                        CallTranscript.call_start_utc <= end,
                    ),
                    CallTranscript,
                    org_id,
                )
            )
        ).scalars().all()

        total_calls = len(transcripts)
        calls_booked = sum(1 for t in transcripts if t.dispatch_job_id is not None)
        calls_escalated = sum(
            1 for t in transcripts if _transcript_is_escalated(t)
        )
        calls_abandoned = sum(
            1
            for t in transcripts
            if t.duration_seconds is not None and t.duration_seconds < 30
        )

        durations = [
            t.duration_seconds for t in transcripts if t.duration_seconds is not None
        ]
        avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

        costs = [
            float(t.call_cost_usd) for t in transcripts if t.call_cost_usd is not None
        ]
        total_cost = round(sum(costs), 2) if costs else 0.0
        booking_rate = (
            round((calls_booked / total_calls) * 100, 1) if total_calls else 0.0
        )
        estimated_bookings_value = round(calls_booked * 150.0, 2)
        roi_multiplier = (
            round(
                ((estimated_bookings_value - total_cost) / total_cost) * 100,
                1,
            )
            if total_cost > 0
            else 0.0
        )

        day_counts: Counter = Counter(
            t.call_start_utc.astimezone(timezone.utc).date() for t in transcripts
        )
        calls_by_day = [
            CallsByDayItem(
                date=(range_start_date + timedelta(days=offset)).isoformat(),
                count=day_counts.get(range_start_date + timedelta(days=offset), 0),
            )
            for offset in range(days)
        ]

        hour_counts: Counter = Counter(
            t.call_start_utc.astimezone(timezone.utc).hour for t in transcripts
        )
        calls_by_hour = [
            CallsByHourItem(hour=hour, count=hour_counts.get(hour, 0))
            for hour in range(24)
        ]

        issue_rows = (
            await self.db.execute(
                scoped(
                    select(DispatchJob.issue_type, func.count())
                    .where(
                        DispatchJob.created_at >= range_start,
                        DispatchJob.created_at <= end,
                    )
                    .group_by(DispatchJob.issue_type)
                    .order_by(func.count().desc())
                    .limit(5),
                    DispatchJob,
                    org_id,
                )
            )
        ).all()
        top_issue_types = [
            TopIssueTypeItem(issue_type=row[0], count=int(row[1])) for row in issue_rows
        ]

        sentiment = SentimentBreakdown(positive=0, neutral=0, negative=0)
        for transcript in transcripts:
            if transcript.sentiment_overall is None:
                sentiment.neutral += 1
                continue
            score = float(transcript.sentiment_overall)
            if score > 0.1:
                sentiment.positive += 1
            elif score < -0.1:
                sentiment.negative += 1
            else:
                sentiment.neutral += 1

        return CallAnalyticsResponse(
            summary=CallAnalyticsSummary(
                total_calls=total_calls,
                calls_booked=calls_booked,
                calls_escalated=calls_escalated,
                calls_abandoned=calls_abandoned,
                booking_rate=booking_rate,
                avg_duration_seconds=avg_duration,
                total_cost_usd=total_cost,
            ),
            revenue_impact=RevenueImpact(
                estimated_bookings_value_usd=estimated_bookings_value,
                ai_cost_usd=total_cost,
                roi_multiplier=roi_multiplier,
            ),
            calls_by_day=calls_by_day,
            calls_by_hour=calls_by_hour,
            top_issue_types=top_issue_types,
            sentiment_breakdown=sentiment,
        )


def _transcript_is_escalated(transcript: CallTranscript) -> bool:
    if transcript.escalation_detected:
        return True
    for field in (transcript.call_summary, transcript.transcript_raw):
        if field and "escalat" in field.lower():
            return True
    if transcript.call_outcome and "escalat" in transcript.call_outcome.lower():
        return True
    return False


def _score_to_tier(score: float) -> str:
    if score >= 0.80:
        return "CRITICAL"
    if score >= 0.60:
        return "HIGH"
    if score >= 0.35:
        return "MEDIUM"
    return "LOW"


def _call_start_label(transcript: CallTranscript) -> str:
    if transcript.escalation_detected:
        return "Inbound complaint — escalation detected"
    if transcript.vapi_metadata and transcript.vapi_metadata.get("recurrence_complaint_detected"):
        return "Inbound complaint: recurrence flagged"
    outcome = transcript.call_outcome or "call"
    return f"Inbound {outcome.replace('_', ' ').lower()}"


def _intervention_label(
    transcript: CallTranscript,
    jobs: list[DispatchJob],
) -> str:
    linked_job = next(
        (job for job in jobs if job.call_transcript_id == transcript.transcript_id),
        None,
    )
    if linked_job:
        return f"P1 Dispatch + retention offer applied (#{linked_job.job_number})"
    if transcript.call_outcome == "DISPATCHED":
        return "Priority dispatch scheduled via voice agent"
    return "AI retention intervention applied"


def _infer_intervention_type(transcript: CallTranscript) -> str:
    if transcript.call_outcome == "DISPATCHED":
        return "PRIORITY_DISPATCH"
    if transcript.call_outcome == "ESCALATED_HUMAN":
        return "MANAGER_CALLBACK"
    if transcript.escalation_detected:
        return "COMPLAINT_ESCALATION"
    return "VOICE_RETENTION"
