from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AvailableSlot(BaseModel):
    date: date
    start_time: time
    end_time: time
    technician_id: uuid.UUID
    technician_name: str
    slot_label: str


class AvailableSlotOut(BaseModel):
    date: str
    start_time: str
    end_time: str
    technician_id: str
    technician_name: str
    slot_label: str


class WorkingHoursEntry(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: str
    end_time: str


class ScheduleOverrideCreate(BaseModel):
    override_date: date
    override_type: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    reason: Optional[str] = None


class ScheduledJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    job_number: str
    customer_id: str
    customer_name: str
    issue_type: str
    issue_description: Optional[str] = None
    technician_id: Optional[str] = None
    technician_name: Optional[str] = None
    priority: str
    job_status: str
    scheduled_window_start: Optional[datetime] = None
    scheduled_window_end: Optional[datetime] = None


class ScheduledJobsResponse(BaseModel):
    org_id: str
    total: int
    items: list[ScheduledJobOut]
