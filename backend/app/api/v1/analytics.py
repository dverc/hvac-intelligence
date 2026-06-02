from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_analytics_service
from app.core.tenant import get_dashboard_org_id
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
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> RetentionEventsResponse:
    return await analytics.get_retention_events(org_id, start, end)


@router.get(
    "/churn-probability-distribution",
    response_model=ChurnDistributionResponse,
)
async def churn_probability_distribution(
    analytics: AnalyticsService = Depends(get_analytics_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> ChurnDistributionResponse:
    return await analytics.get_churn_probability_distribution(org_id)


@router.get("/saved-by-ai", response_model=SavedByAIResponse)
async def saved_by_ai(
    start: datetime = Query(...),
    end: datetime = Query(...),
    analytics: AnalyticsService = Depends(get_analytics_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> SavedByAIResponse:
    return await analytics.get_saved_by_ai(org_id, start, end)


@router.get("/feature-importance", response_model=FeatureImportanceResponse)
async def feature_importance(
    model_version: str = Query(default="latest"),
    analytics: AnalyticsService = Depends(get_analytics_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> FeatureImportanceResponse:
    return await analytics.get_feature_importance(org_id, model_version=model_version)
