from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from app.api.deps import get_analytics_service, get_customer_service
from app.core.auth_jwt import get_current_user
from app.core.tenant import get_dashboard_org_id
from app.ml.counterfactuals import generate_counterfactuals
from app.ml.explainer import build_shap_explanation
from app.ml.feature_engineering import build_customer_features
from app.ml.ground_truth import record_churn_event
from app.ml.model_registry import get_churn_ensemble, load_model
from app.models.call_transcript import CallTranscript
from app.models.churn_score import ChurnScore
from app.models.customer import Customer
from app.schemas.analytics import ChurnTimelineResponse
from app.schemas.customer import CustomerUpdate
from app.schemas.ml_explanations import (
    ChurnOutcomeRequest,
    ChurnOutcomeResponse,
    CounterfactualResponse,
    ShapExplanationResponse,
)
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
    filters = [Customer.org_id == org_id]
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                Customer.full_name.ilike(pattern),
                Customer.phone_primary.ilike(pattern),
                Customer.email.ilike(pattern),
            )
        )
    count_stmt = select(func.count()).select_from(Customer).where(*filters)
    total = (await customer_service.db.execute(count_stmt)).scalar_one()
    offset = (page - 1) * limit

    latest_score = (
        select(
            ChurnScore.entity_id,
            func.max(ChurnScore.score_timestamp).label("max_ts"),
        )
        .where(
            ChurnScore.org_id == org_id,
            ChurnScore.entity_type == "CUSTOMER",
        )
        .group_by(ChurnScore.entity_id)
        .subquery()
    )
    latest_churn = aliased(ChurnScore)
    stmt = (
        select(Customer, latest_churn)
        .outerjoin(
            latest_score,
            latest_score.c.entity_id == Customer.customer_id,
        )
        .outerjoin(
            latest_churn,
            (latest_churn.entity_id == Customer.customer_id)
            & (latest_churn.score_timestamp == latest_score.c.max_ts)
            & (latest_churn.org_id == org_id),
        )
        .where(*filters)
        .order_by(
            latest_churn.churn_probability.desc().nullslast(),
            Customer.full_name,
        )
    )
    rows = (
        await customer_service.db.execute(stmt.offset(offset).limit(limit))
    ).all()

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
                "risk_tier": (
                    latest_churn_row.risk_tier
                    if latest_churn_row is not None
                    else str((c.metadata_ or {}).get("churn_tier", "LOW")).upper()
                ),
                "churn_probability": (
                    float(latest_churn_row.churn_probability)
                    if latest_churn_row is not None
                    else float((c.metadata_ or {}).get("churn_probability", 0.0))
                ),
            }
            for c, latest_churn_row in rows
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


@router.get(
    "/{customer_id}/shap-explanation",
    response_model=ShapExplanationResponse,
)
async def get_customer_shap_explanation(
    customer_id: uuid.UUID,
    customer_service: CustomerService = Depends(get_customer_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    _user: dict = Depends(get_current_user),
) -> ShapExplanationResponse:
    customer = await customer_service.get_by_id(customer_id, org_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    features = await build_customer_features(customer_id, customer_service.db)
    ensemble = get_churn_ensemble()
    model = ensemble.calibrated_model or load_model()
    payload = build_shap_explanation(str(customer_id), features, model)
    return ShapExplanationResponse.model_validate(payload)


@router.get(
    "/{customer_id}/counterfactuals",
    response_model=CounterfactualResponse,
)
async def get_customer_counterfactuals(
    customer_id: uuid.UUID,
    customer_service: CustomerService = Depends(get_customer_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    _user: dict = Depends(get_current_user),
) -> CounterfactualResponse:
    customer = await customer_service.get_by_id(customer_id, org_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    features = await build_customer_features(customer_id, customer_service.db)
    ensemble = get_churn_ensemble()
    model = ensemble.calibrated_model or load_model()
    from app.ml.churn_model import default_rule_score, predict_probability

    current_score = (
        predict_probability(features, model)
        if model is not None
        else default_rule_score(features)
    )
    payload = await generate_counterfactuals(
        customer_id,
        customer_service.db,
        model,
        current_features=features,
        current_score=current_score,
    )
    return CounterfactualResponse.model_validate(payload)


@router.post(
    "/{customer_id}/churn-outcome",
    response_model=ChurnOutcomeResponse,
)
async def post_customer_churn_outcome(
    customer_id: uuid.UUID,
    body: ChurnOutcomeRequest,
    customer_service: CustomerService = Depends(get_customer_service),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    _user: dict = Depends(get_current_user),
) -> ChurnOutcomeResponse:
    customer = await customer_service.get_by_id(customer_id, org_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        label = await record_churn_event(
            customer_id,
            body.churned,
            customer_service.db,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ChurnOutcomeResponse(
        customer_id=str(customer_id),
        churned=body.churned,
        label_id=str(label.label_id),
        churn_probability_at_time=float(label.churn_probability_at_time),
    )
