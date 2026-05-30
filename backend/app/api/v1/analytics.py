from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_analytics_service
from app.schemas.analytics import (
    ChurnDistributionResponse,
    FeatureImportanceResponse,
    RetentionEventsResponse,
    SavedByAIResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/retention-events", response_model=RetentionEventsResponse)
async def retention_events(
    start: datetime = Query(...),
    end: datetime = Query(...),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> RetentionEventsResponse:
    return await analytics.get_retention_events(start, end)


@router.get(
    "/churn-probability-distribution",
    response_model=ChurnDistributionResponse,
)
async def churn_probability_distribution(
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> ChurnDistributionResponse:
    return await analytics.get_churn_probability_distribution()


@router.get("/saved-by-ai", response_model=SavedByAIResponse)
async def saved_by_ai(
    start: datetime = Query(...),
    end: datetime = Query(...),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> SavedByAIResponse:
    return await analytics.get_saved_by_ai(start, end)


@router.get("/feature-importance", response_model=FeatureImportanceResponse)
async def feature_importance(
    model_version: str = Query(default="latest"),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> FeatureImportanceResponse:
    return await analytics.get_feature_importance(model_version=model_version)
