from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select

from app.api.deps import get_analytics_service, get_customer_service
from app.core.tenant import get_dashboard_org_id
from app.models.call_transcript import CallTranscript
from app.models.churn_score import ChurnScore
from app.models.customer import Customer
from app.schemas.analytics import ChurnTimelineResponse
from app.schemas.customer import CustomerUpdate
from app.schemas.transcript import (
    CustomerTranscriptsResponse,
    transcript_to_summary,
)
from app.services.analytics_service import AnalyticsService
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
async def list_customers(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    customer_service: CustomerService = Depends(get_customer_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> dict:
    stmt = select(Customer).where(Customer.org_id == org_id)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Customer.full_name.ilike(pattern),
                Customer.phone_primary.ilike(pattern),
                Customer.email.ilike(pattern),
            )
        )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await customer_service.db.execute(count_stmt)).scalar_one()
    offset = (page - 1) * limit
    rows = (
        await customer_service.db.execute(
            stmt.order_by(Customer.full_name).offset(offset).limit(limit)
        )
    ).scalars().all()

    score_rows = (
        await customer_service.db.execute(
            select(ChurnScore)
            .where(
                ChurnScore.org_id == org_id,
                ChurnScore.entity_type == "CUSTOMER",
            )
            .order_by(ChurnScore.score_timestamp.desc())
        )
    ).scalars().all()
    latest_tier_by_customer: dict[uuid.UUID, str] = {}
    for score in score_rows:
        if score.entity_id not in latest_tier_by_customer:
            latest_tier_by_customer[score.entity_id] = score.risk_tier

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "items": [
            {
                "customer_id": str(c.customer_id),
                "full_name": c.full_name,
                "phone_primary": c.phone_primary,
                "account_status": c.account_status,
                "customer_tier": c.customer_tier,
                "risk_tier": latest_tier_by_customer.get(
                    c.customer_id,
                    str((c.metadata_ or {}).get("churn_tier", "LOW")).upper(),
                ),
            }
            for c in rows
        ],
    }


@router.get("/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID,
    customer_service: CustomerService = Depends(get_customer_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> dict:
    customer = await customer_service.get_by_id(customer_id, org_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return await customer_service.build_customer_profile(customer)


@router.patch("/{customer_id}")
async def patch_customer(
    customer_id: uuid.UUID,
    body: CustomerUpdate,
    customer_service: CustomerService = Depends(get_customer_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> dict:
    if not body.model_fields_set:
        raise HTTPException(status_code=400, detail="No fields to update")
    customer = await customer_service.update_customer(customer_id, body, org_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return await customer_service.build_customer_profile(customer)


@router.get(
    "/{customer_id}/transcripts",
    response_model=CustomerTranscriptsResponse,
)
async def get_customer_transcripts(
    customer_id: uuid.UUID,
    customer_service: CustomerService = Depends(get_customer_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> CustomerTranscriptsResponse:
    rows = (
        await customer_service.db.execute(
            select(CallTranscript)
            .where(
                CallTranscript.org_id == org_id,
                CallTranscript.customer_id == customer_id,
            )
            .order_by(CallTranscript.call_start_utc.desc())
        )
    ).scalars().all()
    return CustomerTranscriptsResponse(
        customer_id=str(customer_id),
        transcripts=[transcript_to_summary(t) for t in rows],
    )


@router.get("/{customer_id}/churn-timeline", response_model=ChurnTimelineResponse)
async def get_customer_churn_timeline(
    customer_id: uuid.UUID,
    analytics: AnalyticsService = Depends(get_analytics_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
) -> ChurnTimelineResponse:
    try:
        return await analytics.get_churn_timeline(org_id, customer_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
