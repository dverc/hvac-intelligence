from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class PortalAppointmentOut(BaseModel):
    id: str
    scheduled_window_start: str | None = None
    scheduled_window_end: str | None = None
    issue_type: str
    issue_description: str | None = None
    job_status: str
    technician_name: str | None = None
    job_number: str


class PortalIdentifyRequest(BaseModel):
    phone: str = Field(min_length=1)


class PortalIdentifyResponse(BaseModel):
    found: bool
    customer_id: str | None = None
    name: str | None = None
    upcoming_appointments: list[PortalAppointmentOut] = Field(default_factory=list)
    past_appointments: list[PortalAppointmentOut] = Field(default_factory=list)


class PortalAppointmentsResponse(BaseModel):
    customer_id: str
    name: str
    upcoming_appointments: list[PortalAppointmentOut]
    past_appointments: list[PortalAppointmentOut]


class PortalServiceRequest(BaseModel):
    phone: str = Field(min_length=1)
    name: str | None = None
    issue_type: str = Field(min_length=1)
    description: str | None = None
    preferred_date: str | None = None
    preferred_time_window: str | None = None


class PortalServiceRequestResponse(BaseModel):
    success: bool
    ticket_number: str
    message: str


class PortalRescheduleRequest(BaseModel):
    customer_id: str
    appointment_id: str
    preferred_date: str = Field(min_length=1)
    preferred_time_window: str = Field(min_length=1)
    reason: str | None = None


class PortalRescheduleResponse(BaseModel):
    success: bool
    message: str


PortalIssueLabel = Literal[
    "AC Not Cooling",
    "AC Not Heating",
    "No Heat",
    "Maintenance",
    "Emergency",
    "Other",
]
