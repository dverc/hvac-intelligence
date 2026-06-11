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
from app.services.portal_service import PortalService

router = APIRouter(prefix="/portal", tags=["portal"])


def _service(db: AsyncSession) -> PortalService:
    return PortalService(db)


@router.post("/identify", response_model=PortalIdentifyResponse)
@limiter.limit("5/minute", override_defaults=True)
async def portal_identify(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PortalIdentifyResponse:
    payload = PortalIdentifyRequest.model_validate(await request.json())
    return await _service(db).identify(payload.phone)


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
        return await _service(db).get_appointments(parsed_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/request", response_model=PortalServiceRequestResponse)
@limiter.limit("3/minute", override_defaults=True)
async def portal_request_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PortalServiceRequestResponse:
    payload = PortalServiceRequest.model_validate(await request.json())
    return await _service(db).request_service(payload)


@router.post("/reschedule-request", response_model=PortalRescheduleResponse)
@limiter.limit("3/minute", override_defaults=True)
async def portal_reschedule_request(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PortalRescheduleResponse:
    payload = PortalRescheduleRequest.model_validate(await request.json())
    try:
        return await _service(db).reschedule_request(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
