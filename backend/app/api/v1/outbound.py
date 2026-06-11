from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_db
from app.core.tenant import get_dashboard_org_id
from app.models.outbound_campaign import OutboundCampaign
from app.schemas.outbound import (
    BlockedAttemptOut,
    CampaignCreate,
    CampaignCustomerOut,
    CampaignExecuteResponse,
    CampaignOut,
    CampaignStatusUpdate,
    ConsentCreate,
    ConsentStatusOut,
    EligibilityOut,
    EligibilityPreview,
)
from app.services.compliance_service import (
    ComplianceService,
    get_disclosure_text,
    get_org_display_name_from_db,
)
from app.services.outbound_service import OutboundService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/outbound", tags=["outbound"])


def _campaign_to_out(campaign: OutboundCampaign) -> CampaignOut:
    conversion = 0.0
    if campaign.total_calls_made > 0:
        conversion = round(campaign.total_booked / campaign.total_calls_made * 100, 1)
    return CampaignOut(
        campaign_id=campaign.campaign_id,
        org_id=campaign.org_id,
        campaign_name=campaign.campaign_name,
        campaign_type=campaign.campaign_type,
        status=campaign.status,
        churn_score_threshold=campaign.churn_score_threshold,
        max_attempts=campaign.max_attempts,
        calling_hours_start=campaign.calling_hours_start,
        calling_hours_end=campaign.calling_hours_end,
        disclosure_style=campaign.disclosure_style,
        total_customers_targeted=campaign.total_customers_targeted,
        total_calls_made=campaign.total_calls_made,
        total_consented=campaign.total_consented,
        total_booked=campaign.total_booked,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        conversion_rate=conversion,
    )


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    if body.calling_hours_start >= body.calling_hours_end:
        raise HTTPException(status_code=422, detail="calling_hours_start must be before end")
    service = OutboundService(db)
    campaign = await service.create_campaign(
        org_id,
        body.model_dump(),
    )
    await db.refresh(campaign)
    return _campaign_to_out(campaign)


@router.get("/campaigns", response_model=list[CampaignOut])
async def list_campaigns(
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[CampaignOut]:
    from sqlalchemy import select

    rows = (
        await db.execute(
            select(OutboundCampaign)
            .where(OutboundCampaign.org_id == org_id)
            .order_by(OutboundCampaign.created_at.desc())
        )
    ).scalars().all()
    return [_campaign_to_out(c) for c in rows]


@router.get("/campaigns/preview-eligible", response_model=EligibilityPreview)
async def preview_eligible_customers(
    churn_score_threshold: float = Query(default=0.75, ge=0.60, le=0.90),
    max_attempts: int = Query(default=2, ge=1, le=3),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> EligibilityPreview:
    service = OutboundService(db)
    count = await service.count_eligible_customers(
        org_id, Decimal(str(churn_score_threshold)), max_attempts
    )
    return EligibilityPreview(
        eligible_count=count,
        churn_score_threshold=churn_score_threshold,
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    campaign = await db.get(OutboundCampaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _campaign_to_out(campaign)


@router.patch("/campaigns/{campaign_id}/status", response_model=CampaignOut)
async def update_campaign_status(
    campaign_id: uuid.UUID,
    body: CampaignStatusUpdate,
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    campaign = await db.get(OutboundCampaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = body.status
    await db.flush()
    return _campaign_to_out(campaign)


@router.get("/campaigns/{campaign_id}/customers", response_model=list[CampaignCustomerOut])
async def get_campaign_customers(
    campaign_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[CampaignCustomerOut]:
    service = OutboundService(db)
    try:
        items = await service.get_campaign_customers(campaign_id, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [CampaignCustomerOut.model_validate(i) for i in items]


@router.post("/campaigns/{campaign_id}/execute", response_model=CampaignExecuteResponse)
async def execute_campaign(
    campaign_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> CampaignExecuteResponse:
    campaign = await db.get(OutboundCampaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status == "RUNNING":
        raise HTTPException(status_code=409, detail="Campaign is already running")
    if campaign.status != "ACTIVE":
        raise HTTPException(
            status_code=400,
            detail="Campaign must be ACTIVE to execute",
        )

    campaign.status = "RUNNING"
    await db.flush()

    from app.tasks.celery_tasks import execute_outbound_campaign

    execute_outbound_campaign.delay(str(campaign_id))
    return CampaignExecuteResponse(
        status="queued",
        message="Campaign execution queued",
        campaign_id=str(campaign_id),
    )


@router.get("/compliance/blocked", response_model=list[BlockedAttemptOut])
async def list_blocked_attempts(
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[BlockedAttemptOut]:
    service = OutboundService(db)
    items = await service.list_blocked_attempts(org_id, limit=20)
    return [BlockedAttemptOut.model_validate(i) for i in items]


@router.post("/consent/{customer_id}", status_code=201)
async def record_consent(
    customer_id: uuid.UUID,
    body: ConsentCreate,
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    compliance = ComplianceService(db)
    record = await compliance.record_consent(
        customer_id,
        org_id,
        body.consent_type,
        body.consent_method,
        body.consent_text,
        call_id=body.call_id,
    )
    return {"consent_id": str(record.consent_id), "status": "recorded"}


@router.delete("/consent/{customer_id}", status_code=200)
async def revoke_consent(
    customer_id: uuid.UUID,
    consent_type: str = Query(default="OUTBOUND_CALL"),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    compliance = ComplianceService(db)
    await compliance.revoke_consent(
        customer_id, org_id, consent_type, "DASHBOARD"
    )
    return {"status": "revoked"}


@router.get("/consent/{customer_id}", response_model=ConsentStatusOut)
async def get_consent_status(
    customer_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> ConsentStatusOut:
    compliance = ComplianceService(db)
    try:
        status = await compliance.get_consent_status(customer_id, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ConsentStatusOut.model_validate(status)


@router.get("/compliance/check/{customer_id}", response_model=EligibilityOut)
async def check_compliance(
    customer_id: uuid.UUID,
    max_attempts: int = Query(default=2, ge=1, le=3),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> EligibilityOut:
    compliance = ComplianceService(db)
    result = await compliance.check_outbound_eligibility(
        customer_id, org_id, max_attempts=max_attempts
    )
    return EligibilityOut.model_validate(result)


@router.get("/compliance/disclosure-preview")
async def disclosure_preview(
    disclosure_style: str = Query(default="FRIENDLY"),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.models.organization import Organization

    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    display_name = await get_org_display_name_from_db(db, org)
    text = get_disclosure_text(display_name, disclosure_style)
    return {"display_name": display_name, "disclosure_text": text}
