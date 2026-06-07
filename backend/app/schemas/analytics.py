"""Dashboard API response shapes (§5.1 + analytics extensions)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskTier = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class CohortBucket(BaseModel):
    tier: RiskTier
    count: int
    percentage: float
    avg_score: float
    estimated_arr_at_risk_usd: float


class WeekOverWeekDelta(BaseModel):
    tier: str
    delta_count: int
    delta_percentage: float


class ChurnDistributionResponse(BaseModel):
    as_of: str
    total_customers: int
    cohorts: list[CohortBucket]
    week_over_week_delta: list[WeekOverWeekDelta]


class MonthlyTrendPoint(BaseModel):
    month: str
    interventions: int
    arr_retained_usd: float
    success_rate: float


class TopInterventionType(BaseModel):
    type: str
    count: int
    avg_score_reduction: float


class SavedByAIResponse(BaseModel):
    period_start: str
    period_end: str
    total_high_risk_calls: int
    successful_interventions: int
    intervention_success_rate: float
    estimated_arr_retained_usd: float
    avg_score_reduction: float
    monthly_trend: list[MonthlyTrendPoint]
    top_intervention_types: list[TopInterventionType]


class RetentionEventItem(BaseModel):
    event_id: str
    timestamp: str
    event_type: Literal[
        "CALL_START",
        "INTERVENTION_APPLIED",
        "DISPATCH_CREATED",
        "SCORE_CHANGE",
        "TICKET_RESOLVED",
        "CHURNED",
    ]
    customer_id: str
    customer_name: str
    label: str
    call_id: str | None = None
    churn_probability_before: float | None = None
    churn_probability_after: float | None = None
    risk_tier: str | None = None
    saved_by_ai: bool = False


class RetentionEventsResponse(BaseModel):
    period_start: str
    period_end: str
    events: list[RetentionEventItem]


class FeatureImportanceItem(BaseModel):
    feature: str
    importance: float
    avg_shap_value: float
    direction: Literal["INCREASES_RISK", "DECREASES_RISK"]


class FeatureImportanceResponse(BaseModel):
    model_version: str | None
    as_of: str
    source: Literal["aggregated_churn_scores", "no_contributions"]
    features: list[FeatureImportanceItem]


class TimelineEvent(BaseModel):
    type: Literal[
        "CALL_START",
        "DISPATCH_CREATED",
        "INTERVENTION_APPLIED",
        "TICKET_RESOLVED",
        "CHURNED",
    ]
    label: str
    call_id: str | None = None


class ChurnTimelinePoint(BaseModel):
    timestamp: str
    churn_probability: float
    risk_tier: str
    event: TimelineEvent | None = None


class CohortBucketSample(BaseModel):
    customer_id: str
    name: str
    score: float


class CohortHeatmapBucket(BaseModel):
    score_range_low: float
    score_range_high: float
    customer_count: int
    avg_arr_usd: float
    intervention_success_rate: float
    top_features: list[str]
    customers_sample: list[CohortBucketSample]


class CohortHeatmapResponse(BaseModel):
    generated_at: str
    buckets: list[CohortHeatmapBucket]


class ChurnTimelineResponse(BaseModel):
    customer_id: str
    customer_name: str
    data_points: list[ChurnTimelinePoint]
    current_score: float
    score_90d_ago: float
    net_change: float
    interventions_count: int
    saved_by_ai: bool


class CallAnalyticsSummary(BaseModel):
    total_calls: int
    calls_booked: int
    calls_escalated: int
    calls_abandoned: int
    booking_rate: float
    avg_duration_seconds: float
    total_cost_usd: float


class RevenueImpact(BaseModel):
    estimated_bookings_value_usd: float
    ai_cost_usd: float
    roi_multiplier: float


class CallsByDayItem(BaseModel):
    date: str
    count: int


class CallsByHourItem(BaseModel):
    hour: int
    count: int


class TopIssueTypeItem(BaseModel):
    issue_type: str
    count: int


class SentimentBreakdown(BaseModel):
    positive: int
    neutral: int
    negative: int


class CallAnalyticsResponse(BaseModel):
    summary: CallAnalyticsSummary
    revenue_impact: RevenueImpact
    calls_by_day: list[CallsByDayItem]
    calls_by_hour: list[CallsByHourItem]
    top_issue_types: list[TopIssueTypeItem]
    sentiment_breakdown: SentimentBreakdown
