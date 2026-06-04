from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_availability_service
from app.core.tenant import get_dashboard_org_id
from app.schemas.scheduling import (
    AvailableSlotOut,
    ScheduledJobOut,
    ScheduledJobsResponse,
    ScheduleOverrideCreate,
    WorkingHoursEntry,
)
from app.services.availability_service import AvailabilityService, _parse_hhmm

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


@router.get("/availability", response_model=list[AvailableSlotOut])
async def get_availability(
    date_from: date = Query(...),
    date_to: date = Query(...),
    technician_id: uuid.UUID | None = Query(default=None),
    duration_minutes: int = Query(default=60, ge=30, le=480),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    availability: AvailabilityService = Depends(get_availability_service),
) -> list[AvailableSlotOut]:
    slots = await availability.get_available_slots(
        org_id=org_id,
        date_range_start=date_from,
        date_range_end=date_to,
        duration_minutes=duration_minutes,
        preferred_technician_id=technician_id,
    )
    return [
        AvailableSlotOut(
            date=s.date.isoformat(),
            start_time=s.start_time.strftime("%H:%M"),
            end_time=s.end_time.strftime("%H:%M"),
            technician_id=str(s.technician_id),
            technician_name=s.technician_name,
            slot_label=s.slot_label,
        )
        for s in slots
    ]


@router.get("/technicians/{tech_id}/schedule")
async def get_technician_schedule(
    tech_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    availability: AvailabilityService = Depends(get_availability_service),
) -> dict:
    result = await availability.get_technician_schedule(org_id, tech_id, date_from, date_to)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="Technician not found")
    return result


@router.put("/technicians/{tech_id}/working-hours")
async def set_working_hours(
    tech_id: uuid.UUID,
    entries: list[WorkingHoursEntry],
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    availability: AvailabilityService = Depends(get_availability_service),
) -> dict:
    updated = []
    try:
        for entry in entries:
            row = await availability.set_working_hours(
                org_id,
                tech_id,
                entry.day_of_week,
                _parse_hhmm(entry.start_time),
                _parse_hhmm(entry.end_time),
            )
            updated.append(
                {
                    "day_of_week": row.day_of_week,
                    "start_time": row.start_time.strftime("%H:%M"),
                    "end_time": row.end_time.strftime("%H:%M"),
                }
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"technician_id": str(tech_id), "working_hours": updated}


@router.post("/technicians/{tech_id}/overrides")
async def create_override(
    tech_id: uuid.UUID,
    payload: ScheduleOverrideCreate,
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    availability: AvailabilityService = Depends(get_availability_service),
) -> dict:
    start_t = _parse_hhmm(payload.start_time) if payload.start_time else None
    end_t = _parse_hhmm(payload.end_time) if payload.end_time else None
    try:
        row = await availability.add_override(
            org_id,
            tech_id,
            payload.override_date,
            payload.override_type,
            start_time=start_t,
            end_time=end_t,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "override_id": str(row.override_id),
        "override_date": row.override_date.isoformat(),
        "override_type": row.override_type,
    }


@router.get("/jobs", response_model=ScheduledJobsResponse)
async def list_scheduled_jobs(
    date_from: date = Query(...),
    date_to: date = Query(...),
    technician_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    availability: AvailabilityService = Depends(get_availability_service),
) -> ScheduledJobsResponse:
    items = await availability.list_scheduled_jobs(
        org_id, date_from, date_to, technician_id, status
    )
    return ScheduledJobsResponse(
        org_id=str(org_id),
        total=len(items),
        items=[ScheduledJobOut(**item) for item in items],
    )
