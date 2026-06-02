from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.deps import get_analytics_service, get_churn_service
from app.core.tenant import get_dashboard_org_id
from app.models.churn_score import ChurnScore
from app.schemas.analytics import CohortHeatmapResponse
from app.services.analytics_service import AnalyticsService
from app.services.churn_service import ChurnService

router = APIRouter(prefix="/churn", tags=["churn"])


@router.get("/scores")
async def list_churn_scores(
    entity_type: str = Query(default="CUSTOMER"),
    risk_tier: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    churn_service: ChurnService = Depends(get_churn_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> dict:
    stmt = select(ChurnScore).where(
        ChurnScore.org_id == org_id,
        ChurnScore.entity_type == entity_type,
    )
    if risk_tier:
        stmt = stmt.where(ChurnScore.risk_tier == risk_tier.upper())
    stmt = stmt.order_by(ChurnScore.score_timestamp.desc()).limit(limit)
    rows = (await churn_service.db.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "score_id": str(r.score_id),
                "entity_type": r.entity_type,
                "entity_id": str(r.entity_id),
                "churn_probability": float(r.churn_probability),
                "risk_tier": r.risk_tier,
                "score_timestamp": r.score_timestamp.isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/scores/{entity_id}/history")
async def churn_score_history(
    entity_id: uuid.UUID,
    days: int = Query(default=90, ge=1, le=365),
    churn_service: ChurnService = Depends(get_churn_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> dict:
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await churn_service.db.execute(
            select(ChurnScore)
            .where(
                ChurnScore.org_id == org_id,
                ChurnScore.entity_id == entity_id,
                ChurnScore.score_timestamp >= since,
            )
            .order_by(ChurnScore.score_timestamp.asc())
        )
    ).scalars().all()
    return {
        "entity_id": str(entity_id),
        "days": days,
        "history": [
            {
                "churn_probability": float(r.churn_probability),
                "risk_tier": r.risk_tier,
                "score_timestamp": r.score_timestamp.isoformat(),
            }
            for r in rows
        ],
    }


@router.post("/scores/{entity_id}/trigger")
async def trigger_churn_score(
    entity_id: uuid.UUID,
    churn_service: ChurnService = Depends(get_churn_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> dict:
    try:
        score = await churn_service.get_latest_score(str(entity_id), org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "queued", "entity_id": str(entity_id), "latest_snapshot": score}


@router.get("/cohorts", response_model=CohortHeatmapResponse)
async def churn_cohorts(
    window_days: int = Query(default=90, ge=1),
    bucket_count: int = Query(default=10, ge=1, le=20),
    analytics: AnalyticsService = Depends(get_analytics_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> CohortHeatmapResponse:
    return await analytics.get_cohort_heatmap(
        org_id,
        window_days=window_days,
        bucket_count=bucket_count,
    )
