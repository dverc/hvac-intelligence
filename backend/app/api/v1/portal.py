from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.rate_limit import limiter
from app.schemas.portal import (
    PortalAppointmentsResponse,
    PortalIdentifyRequest,
    PortalIdentifyResponse,
    PortalRescheduleRequest,
    PortalRescheduleResponse,
    PortalServiceRequest,
    PortalServiceRequestResponse,
)
from app.services.portal_service import PortalService, resolve_portal_org_id

router = APIRouter(prefix="/portal", tags=["portal"])


def _service(db: AsyncSession, org_id: uuid.UUID) -> PortalService:
    return PortalService(db, org_id)


async def _resolve_portal_org_or_400(
    request: Request, db: AsyncSession
) -> uuid.UUID:
    org_id = await resolve_portal_org_id(request.query_params.get("org"), db)
    if org_id is None:
        raise HTTPException(status_code=400, detail="org parameter required")
    return org_id


@router.post("/identify", response_model=PortalIdentifyResponse)
@limiter.limit("5/minute", override_defaults=True)
async def portal_identify(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PortalIdentifyResponse:
    payload = PortalIdentifyRequest.model_validate(await request.json())
    org_id = await _resolve_portal_org_or_400(request, db)
    return await _service(db, org_id).identify(payload.phone)


@router.get(
    "/appointments/{customer_id}",
    response_model=PortalAppointmentsResponse,
)
@limiter.limit("10/minute", override_defaults=True)
async def portal_appointments(
    request: Request,
    customer_id: str,
    db: AsyncSession = Depends(get_db),
) -> PortalAppointmentsResponse:
    try:
        parsed_id = uuid.UUID(customer_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Customer not found") from exc
    try:
        org_id = await _resolve_portal_org_or_400(request, db)
        return await _service(db, org_id).get_appointments(parsed_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/request", response_model=PortalServiceRequestResponse)
@limiter.limit("3/minute", override_defaults=True)
async def portal_request_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PortalServiceRequestResponse:
    payload = PortalServiceRequest.model_validate(await request.json())
    org_id = await _resolve_portal_org_or_400(request, db)
    return await _service(db, org_id).request_service(payload)


@router.post("/reschedule-request", response_model=PortalRescheduleResponse)
@limiter.limit("3/minute", override_defaults=True)
async def portal_reschedule_request(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PortalRescheduleResponse:
    payload = PortalRescheduleRequest.model_validate(await request.json())
    try:
        org_id = await _resolve_portal_org_or_400(request, db)
        return await _service(db, org_id).reschedule_request(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
