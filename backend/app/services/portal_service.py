from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.tenant import get_fallback_dashboard_org_id
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.org_settings import OrgSettings
from app.models.support_ticket import SupportTicket
from app.schemas.portal import (
    PortalAppointmentOut,
    PortalAppointmentsResponse,
    PortalIdentifyResponse,
    PortalRescheduleRequest,
    PortalRescheduleResponse,
    PortalServiceRequest,
    PortalServiceRequestResponse,
)
from app.services.customer_service import CustomerService, normalize_phone
from app.services.ticket_service import TicketService

DEFAULT_PORTAL_TZ = "America/Los_Angeles"

ISSUE_TYPE_MAP: dict[str, str] = {
    "AC Not Cooling": "AC_FAILURE",
    "AC Not Heating": "AC_FAILURE",
    "No Heat": "HEATING_FAILURE",
    "Maintenance": "MAINTENANCE",
    "Emergency": "EMERGENCY",
    "Other": "GENERAL",
}


def _format_dt_in_tz(value: datetime | None, tz: ZoneInfo) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz).isoformat()


def _serialize_appointment(job: DispatchJob, tz: ZoneInfo) -> PortalAppointmentOut:
    tech_name = job.technician.full_name if job.technician else None
    return PortalAppointmentOut(
        id=str(job.job_id),
        scheduled_window_start=_format_dt_in_tz(job.scheduled_window_start, tz),
        scheduled_window_end=_format_dt_in_tz(job.scheduled_window_end, tz),
        issue_type=job.issue_type,
        issue_description=job.issue_description,
        job_status=job.job_status,
        technician_name=tech_name,
        job_number=job.job_number,
    )


def _ticket_number(ticket_id: uuid.UUID) -> str:
    return f"TKT-{str(ticket_id).replace('-', '')[:8].upper()}"


class PortalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.customers = CustomerService(db)
        self.tickets = TicketService(db)

    def _org_id(self) -> uuid.UUID:
        return get_fallback_dashboard_org_id()

    async def _get_org_timezone(self, org_id: uuid.UUID) -> ZoneInfo:
        tz_name = (
            await self.db.execute(
                select(OrgSettings.timezone).where(OrgSettings.org_id == org_id)
            )
        ).scalar_one_or_none()
        return ZoneInfo(tz_name or DEFAULT_PORTAL_TZ)

    async def _load_appointments(
        self, customer_id: uuid.UUID
    ) -> tuple[list[PortalAppointmentOut], list[PortalAppointmentOut]]:
        org_id = self._org_id()
        portal_tz = await self._get_org_timezone(org_id)
        now = datetime.now(timezone.utc)
        stmt = (
            select(DispatchJob)
            .where(
                DispatchJob.customer_id == customer_id,
                DispatchJob.org_id == self._org_id(),
                DispatchJob.scheduled_window_start.is_not(None),
            )
            .options(selectinload(DispatchJob.technician))
        )
        jobs = (await self.db.execute(stmt)).scalars().all()

        upcoming = sorted(
            [j for j in jobs if j.scheduled_window_start and j.scheduled_window_start >= now],
            key=lambda j: j.scheduled_window_start or now,
        )
        past = sorted(
            [j for j in jobs if j.scheduled_window_start and j.scheduled_window_start < now],
            key=lambda j: j.scheduled_window_start or now,
            reverse=True,
        )[:10]

        return (
            [_serialize_appointment(j, portal_tz) for j in upcoming],
            [_serialize_appointment(j, portal_tz) for j in past],
        )

    async def identify(self, phone: str) -> PortalIdentifyResponse:
        org_id = self._org_id()
        customer = await self.customers.lookup_by_phone(phone, org_id)
        if customer is None:
            return PortalIdentifyResponse(found=False)

        upcoming, past = await self._load_appointments(customer.customer_id)
        return PortalIdentifyResponse(
            found=True,
            customer_id=str(customer.customer_id),
            name=customer.full_name,
            upcoming_appointments=upcoming,
            past_appointments=past,
        )

    async def get_appointments(self, customer_id: uuid.UUID) -> PortalAppointmentsResponse:
        org_id = self._org_id()
        customer = await self.customers.get_by_id(customer_id, org_id)
        if customer is None:
            raise ValueError("Customer not found")

        upcoming, past = await self._load_appointments(customer.customer_id)
        return PortalAppointmentsResponse(
            customer_id=str(customer.customer_id),
            name=customer.full_name,
            upcoming_appointments=upcoming,
            past_appointments=past,
        )

    async def _get_or_create_customer(
        self, phone: str, name: str | None
    ) -> Customer:
        org_id = self._org_id()
        existing = await self.customers.lookup_by_phone(phone, org_id)
        if existing is not None:
            return existing

        normalized = normalize_phone(phone)
        customer = Customer(
            org_id=org_id,
            full_name=(name or "Portal Customer").strip() or "Portal Customer",
            phone_primary=normalized,
            customer_since=date.today(),
            account_status="PROSPECT",
            contract_type="RESIDENTIAL_OTC",
        )
        self.db.add(customer)
        await self.db.flush()
        return customer

    def _build_callback_description(
        self,
        *,
        issue_type: str,
        description: str | None,
        preferred_date: str | None,
        preferred_time_window: str | None,
        extra: str | None = None,
    ) -> str:
        lines = [
            f"Issue type: {issue_type}",
            f"Mapped issue: {ISSUE_TYPE_MAP.get(issue_type, 'GENERAL')}",
        ]
        if description:
            lines.append(f"Description: {description}")
        if preferred_date:
            lines.append(f"Preferred date: {preferred_date}")
        if preferred_time_window:
            lines.append(f"Preferred time window: {preferred_time_window}")
        if extra:
            lines.append(extra)
        lines.append("Source: customer portal")
        return "\n".join(lines)

    async def request_service(
        self, body: PortalServiceRequest
    ) -> PortalServiceRequestResponse:
        customer = await self._get_or_create_customer(body.phone, body.name)
        org_id = self._org_id()
        subject = f"Portal service request: {body.issue_type}"
        description = self._build_callback_description(
            issue_type=body.issue_type,
            description=body.description,
            preferred_date=body.preferred_date,
            preferred_time_window=body.preferred_time_window,
        )
        ticket_data = await self.tickets.create_ticket(
            customer_id=customer.customer_id,
            org_id=org_id,
            ticket_type="MANAGER_CALLBACK",
            subject=subject,
            description=description,
            priority="P2" if body.issue_type == "Emergency" else "P3",
            preferred_callback_time=body.preferred_time_window,
            created_by="PORTAL",
        )
        ticket_id = uuid.UUID(ticket_data["ticket_id"])
        return PortalServiceRequestResponse(
            success=True,
            ticket_number=_ticket_number(ticket_id),
            message=(
                "Your service request has been received. "
                "We'll contact you within 2 hours during business hours."
            ),
        )

    async def reschedule_request(
        self, body: PortalRescheduleRequest
    ) -> PortalRescheduleResponse:
        org_id = self._org_id()
        try:
            customer_id = uuid.UUID(body.customer_id)
            appointment_id = uuid.UUID(body.appointment_id)
        except ValueError as exc:
            raise ValueError("Invalid customer or appointment id") from exc

        customer = await self.customers.get_by_id(customer_id, org_id)
        if customer is None:
            raise ValueError("Customer not found")

        job = await self.db.get(DispatchJob, appointment_id)
        if (
            job is None
            or job.customer_id != customer_id
            or job.org_id != org_id
        ):
            raise ValueError("Appointment not found")

        portal_tz = await self._get_org_timezone(org_id)
        subject = f"Portal reschedule request for {job.job_number}"
        extra = (
            f"Appointment: {job.job_number}\n"
            f"Current window start: {_format_dt_in_tz(job.scheduled_window_start, portal_tz)}\n"
            f"Current window end: {_format_dt_in_tz(job.scheduled_window_end, portal_tz)}"
        )
        if body.reason:
            extra += f"\nReason: {body.reason}"

        description = self._build_callback_description(
            issue_type="Reschedule",
            description=body.reason,
            preferred_date=body.preferred_date,
            preferred_time_window=body.preferred_time_window,
            extra=extra,
        )
        await self.tickets.create_ticket(
            customer_id=customer_id,
            org_id=org_id,
            ticket_type="MANAGER_CALLBACK",
            subject=subject,
            description=description,
            priority="P3",
            preferred_callback_time=body.preferred_time_window,
            created_by="PORTAL",
        )
        return PortalRescheduleResponse(
            success=True,
            message=(
                "Reschedule request submitted. We'll contact you to confirm the new time."
            ),
        )

    @staticmethod
    def support_phone() -> str | None:
        settings = get_settings()
        phone = (settings.VAPI_PHONE_NUMBER or "").strip()
        return phone or None
