from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.organization import Organization
from app.models.technician import Technician
from app.schemas.organization import OrganizationSettings
from app.schemas.tools import UpdateDispatchArgs
from app.services.availability_service import AvailabilityService
from app.services.google_calendar_service import GoogleCalendarService
from app.services.jobber_service import JobberService
from app.services.window_parser import ParsedWindow, parse_preferred_window

logger = logging.getLogger(__name__)


def _generate_job_number() -> str:
    return f"DX-{random.randint(1000, 9999)}"


def _apply_retention_priority(
    priority: str, churn_context: Optional[dict[str, Any]]
) -> tuple[str, bool]:
    if not churn_context:
        return priority, False
    tier = str(churn_context.get("risk_tier", "")).upper()
    if tier in {"HIGH", "CRITICAL"} and priority in {"P3", "P4"}:
        return "P2", True
    if tier == "CRITICAL" and priority == "P2":
        return "P1", True
    return priority, tier in {"HIGH", "CRITICAL"}


class DispatchService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.availability = AvailabilityService(db)

    async def _get_org_timezone(self, org_id: uuid.UUID) -> str:
        org = await self.db.get(Organization, org_id)
        if org is None:
            return "America/Los_Angeles"
        settings = OrganizationSettings.model_validate(org.settings or {})
        return settings.timezone

    async def _resolve_preferred_window(
        self,
        preferred_window: str,
        org_id: uuid.UUID,
        technician_id: uuid.UUID,
        tz_name: str | None = None,
    ) -> ParsedWindow:
        """Parse preferred_window; fall back to first open slot when time is unknown."""
        if tz_name is None:
            tz_name = await self._get_org_timezone(org_id)
        parsed = parse_preferred_window(preferred_window, tz_name)
        if parsed.times_resolved:
            return parsed

        slots = await self.availability.get_available_slots(
            org_id,
            parsed.slot_date,
            parsed.slot_date,
            duration_minutes=120,
            preferred_technician_id=technician_id,
        )
        if not slots:
            return parsed

        slot = slots[0]
        return ParsedWindow(
            slot_date=slot.date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            times_resolved=True,
        )

    async def _select_technician(
        self, customer: Customer, org_id: uuid.UUID
    ) -> Technician:
        if customer.preferred_tech_id:
            tech = await self.db.get(Technician, customer.preferred_tech_id)
            if (
                tech
                and tech.org_id == org_id
                and tech.employment_status == "ACTIVE"
            ):
                return tech

        stmt = (
            select(Technician)
            .where(
                Technician.org_id == org_id,
                Technician.employment_status == "ACTIVE",
            )
            .order_by(Technician.avg_customer_rating.desc().nullslast())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        tech = result.scalar_one_or_none()
        if tech is None:
            raise ValueError("No active technicians available for dispatch")
        return tech

    async def create_job(
        self,
        customer_id: str,
        issue_type: str,
        priority: str,
        preferred_window: str,
        issue_description: str,
        org_id: uuid.UUID,
        equipment_id: Optional[str] = None,
        access_instructions: Optional[str] = None,
        churn_context: Optional[dict[str, Any]] = None,
        preferred_technician_id: Optional[uuid.UUID] = None,
    ) -> dict[str, Any]:
        cid = uuid.UUID(customer_id)
        customer = await self.db.get(
            Customer, cid, options=[selectinload(Customer.preferred_tech)]
        )
        if customer is None or customer.org_id != org_id:
            raise ValueError(f"Customer {customer_id} not found")

        applied_priority, retention_flag = _apply_retention_priority(priority, churn_context)
        if preferred_technician_id is not None:
            tech = await self.db.get(Technician, preferred_technician_id)
            if (
                tech
                and tech.org_id == org_id
                and tech.employment_status == "ACTIVE"
            ):
                technician = tech
            else:
                technician = await self._select_technician(customer, org_id)
        else:
            technician = await self._select_technician(customer, org_id)
        tz_name = await self._get_org_timezone(org_id)
        parsed = await self._resolve_preferred_window(
            preferred_window, org_id, technician.technician_id, tz_name
        )
        if not parsed.times_resolved:
            return {
                "success": False,
                "error": "no_availability",
                "message": (
                    f"No open slots found for {preferred_window}. "
                    "Call check_availability to find open times."
                ),
            }

        available, reason = await self.availability.check_slot_available(
            org_id,
            technician.technician_id,
            parsed.slot_date,
            parsed.start_time,
            parsed.end_time,
        )
        if not available:
            first_name = technician.full_name.split()[0]
            return {
                "success": False,
                "error": "conflict",
                "message": (
                    f"{technician.full_name} is not available "
                    f"{preferred_window}. {reason} "
                    "Call check_availability to find open slots."
                ),
            }

        window_start, window_end = parsed.to_datetimes(tz_name)

        job_number = _generate_job_number()
        for _ in range(5):
            existing = await self.db.execute(
                select(DispatchJob).where(
                    DispatchJob.org_id == org_id,
                    DispatchJob.job_number == job_number,
                )
            )
            if existing.scalar_one_or_none() is None:
                break
            job_number = _generate_job_number()

        description = issue_description
        if access_instructions:
            description = f"{issue_description}\n\nAccess: {access_instructions}"

        job = DispatchJob(
            job_number=job_number,
            org_id=org_id,
            customer_id=cid,
            equipment_id=uuid.UUID(equipment_id) if equipment_id else None,
            technician_id=technician.technician_id,
            job_status="SCHEDULED",
            priority=applied_priority,
            issue_type=issue_type,
            issue_description=description,
            scheduled_window_start=window_start,
            scheduled_window_end=window_end,
            created_by="VOICE_AGENT",
        )
        self.db.add(job)
        await self.db.flush()

        gcal = GoogleCalendarService(self.db)
        if await gcal.has_active_connection(org_id):
            try:
                event_id = await gcal.create_calendar_event(
                    org_id, job, technician, customer
                )
                job.google_calendar_event_id = event_id
                await self.db.flush()
            except Exception as exc:
                logger.exception(
                    "Google Calendar event creation failed for job %s: %s",
                    job.job_number,
                    exc,
                )

        jobber = JobberService(self.db)
        if await jobber.has_active_connection(org_id):
            try:
                await jobber.create_job_in_jobber(org_id, job, customer, technician)
            except Exception as exc:
                logger.exception(
                    "Jobber job creation failed for job %s: %s",
                    job.job_number,
                    exc,
                )

        tech_row = await self.db.execute(
            select(Technician).where(Technician.technician_id == technician.technician_id)
        )
        tech = tech_row.scalar_one()
        first_name = tech.full_name.split()[0]

        return {
            "success": True,
            "job_id": str(job.job_id),
            "job_number": job.job_number,
            "technician": {
                "name": f"{first_name} {tech.full_name.split()[-1][0]}.",
                "certifications": tech.certifications or [],
                "rating": float(tech.avg_customer_rating)
                if tech.avg_customer_rating is not None
                else None,
            },
            "scheduled_window": {
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            },
            "priority_applied": applied_priority,
            "retention_flag": retention_flag,
            "human_readable": (
                f"{first_name} will arrive "
                f"{preferred_window}. Confirmation: {job.job_number}."
            ),
        }

    async def update_job(
        self, args: UpdateDispatchArgs, org_id: uuid.UUID
    ) -> dict[str, Any]:
        job = await self.db.get(DispatchJob, uuid.UUID(args.job_id))
        if job is None or job.org_id != org_id:
            return {"success": False, "error": f"Dispatch job {args.job_id} not found"}

        changes: list[str] = []
        description = job.issue_description or ""
        tz_name = await self._get_org_timezone(org_id)

        if args.cancel:
            job.job_status = "CANCELLED"
            changes.append("booking cancelled")

        if args.preferred_window:
            if job.technician_id:
                parsed = await self._resolve_preferred_window(
                    args.preferred_window,
                    org_id,
                    job.technician_id,
                    tz_name,
                )
            else:
                parsed = parse_preferred_window(args.preferred_window, tz_name)
            if job.technician_id:
                available, reason = await self.availability.check_slot_available(
                    org_id,
                    job.technician_id,
                    parsed.slot_date,
                    parsed.start_time,
                    parsed.end_time,
                )
                if not available:
                    return {
                        "success": False,
                        "error": "conflict",
                        "message": reason,
                    }
            window_start, window_end = parsed.to_datetimes(tz_name)
            job.scheduled_window_start = window_start
            job.scheduled_window_end = window_end
            changes.append(f"window updated to {args.preferred_window}")

        if args.service_address_override:
            correction = f"ADDRESS CORRECTION: {args.service_address_override}"
            description = f"{description}\n\n{correction}".strip() if description else correction
            changes.append("service address corrected")

        if args.notes:
            note_line = f"NOTE: {args.notes}"
            description = f"{description}\n\n{note_line}".strip() if description else note_line
            changes.append("notes added")

        if description != (job.issue_description or ""):
            job.issue_description = description

        if not changes:
            return {
                "success": True,
                "job_id": str(job.job_id),
                "job_number": job.job_number,
                "message": "No changes were requested.",
                "changes": [],
            }

        await self.db.flush()

        if job.google_calendar_event_id:
            gcal = GoogleCalendarService(self.db)
            try:
                if args.cancel:
                    await gcal.delete_calendar_event(org_id, job.google_calendar_event_id)
                else:
                    tech = await self.db.get(Technician, job.technician_id)
                    customer = await self.db.get(Customer, job.customer_id)
                    if tech and customer:
                        await gcal.update_calendar_event(
                            org_id,
                            job.google_calendar_event_id,
                            job,
                            tech,
                            customer,
                        )
            except Exception as exc:
                logger.exception(
                    "Google Calendar sync failed for job %s: %s",
                    job.job_number,
                    exc,
                )

        summary = ", ".join(changes)
        return {
            "success": True,
            "job_id": str(job.job_id),
            "job_number": job.job_number,
            "job_status": job.job_status,
            "changes": changes,
            "message": f"Booking updated. {summary.capitalize()}.",
        }
