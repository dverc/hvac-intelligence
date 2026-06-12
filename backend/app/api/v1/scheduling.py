from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_availability_service, get_db
from app.core.tenant import get_dashboard_org_id
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.technician import Technician
from app.schemas.scheduling import (
    AvailableSlotOut,
    ScheduledJobOut,
    ScheduledJobsResponse,
    ScheduleOverrideCreate,
    WorkingHoursEntry,
)
from app.services.availability_service import AvailabilityService, _parse_hhmm

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


async def _list_recently_completed_dispatch_jobs(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    technician_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    availability = AvailabilityService(db)
    tz_name = await availability._get_org_timezone(org_id)
    tz = ZoneInfo(tz_name)
    range_start = datetime.combine(date_from, time.min, tzinfo=tz)
    range_end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)
    completed_at = func.coalesce(DispatchJob.actual_completion, DispatchJob.updated_at)

    stmt = (
        select(
            DispatchJob.job_id,
            DispatchJob.job_number,
            DispatchJob.job_status,
            DispatchJob.priority,
            DispatchJob.issue_type,
            DispatchJob.scheduled_window_start,
            DispatchJob.scheduled_window_end,
            DispatchJob.technician_id,
            DispatchJob.customer_id,
            Customer.full_name.label("customer_name"),
            Technician.full_name.label("technician_name"),
        )
        .join(Customer, DispatchJob.customer_id == Customer.customer_id)
        .outerjoin(Technician, DispatchJob.technician_id == Technician.technician_id)
        .where(
            DispatchJob.org_id == org_id,
            Customer.org_id == org_id,
            DispatchJob.job_status == "COMPLETED",
            completed_at >= range_start,
            completed_at < range_end,
        )
        .order_by(completed_at.desc())
        .limit(limit)
    )
    if technician_id:
        stmt = stmt.where(DispatchJob.technician_id == technician_id)

    rows = (await db.execute(stmt)).all()
    return [
        {
            "job_id": str(row.job_id),
            "job_number": row.job_number,
            "customer_id": str(row.customer_id),
            "customer_name": row.customer_name,
            "issue_type": row.issue_type,
            "technician_id": str(row.technician_id) if row.technician_id else None,
            "technician_name": row.technician_name,
            "priority": row.priority,
            "job_status": row.job_status,
            "scheduled_window_start": row.scheduled_window_start,
            "scheduled_window_end": row.scheduled_window_end,
        }
        for row in rows
    ]


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


@router.get("/jobs/completed", response_model=ScheduledJobsResponse)
async def list_recently_completed_dispatch_jobs(
    date_from: date = Query(...),
    date_to: date = Query(...),
    technician_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    db: AsyncSession = Depends(get_db),
) -> ScheduledJobsResponse:
    items = await _list_recently_completed_dispatch_jobs(
        db, org_id, date_from, date_to, technician_id, limit
    )
    return ScheduledJobsResponse(
        org_id=str(org_id),
        total=len(items),
        items=[ScheduledJobOut(**item) for item in items],
    )


@router.get("/jobs", response_model=ScheduledJobsResponse)
async def list_scheduled_jobs(
    date_from: date = Query(...),
    date_to: date = Query(...),
    technician_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    org_id: uuid.UUID = Depends(get_dashboard_org_id),
    availability: AvailabilityService = Depends(get_availability_service),
    db: AsyncSession = Depends(get_db),
) -> ScheduledJobsResponse:
    if status and status.upper() == "COMPLETED":
        items = await _list_recently_completed_dispatch_jobs(
            db, org_id, date_from, date_to, technician_id
        )
    else:
        items = await availability.list_scheduled_jobs(
            org_id, date_from, date_to, technician_id, status
        )
    return ScheduledJobsResponse(
        org_id=str(org_id),
        total=len(items),
        items=[ScheduledJobOut(**item) for item in items],
    )
