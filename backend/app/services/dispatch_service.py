from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.technician import Technician
from app.schemas.tools import UpdateDispatchArgs


def _generate_job_number() -> str:
    return f"DX-{random.randint(1000, 9999)}"


def _parse_preferred_window(preferred_window: str) -> tuple[datetime, datetime]:
    """Map natural-language windows to UTC timestamps (simplified heuristic)."""
    now = datetime.now(timezone.utc)
    lower = preferred_window.lower()
    if "tomorrow" in lower and "afternoon" in lower:
        start = (now + timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=3)
    elif "tomorrow" in lower or "next day" in lower:
        start = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
    elif "today" in lower or "same day" in lower:
        start = now + timedelta(hours=2)
        end = start + timedelta(hours=2)
    else:
        start = (now + timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=4)
    return start, end


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

    async def _select_technician(self, customer: Customer) -> Technician:
        if customer.preferred_tech_id:
            tech = await self.db.get(Technician, customer.preferred_tech_id)
            if tech and tech.employment_status == "ACTIVE":
                return tech

        stmt = (
            select(Technician)
            .where(Technician.employment_status == "ACTIVE")
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
        equipment_id: Optional[str] = None,
        access_instructions: Optional[str] = None,
        churn_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        cid = uuid.UUID(customer_id)
        customer = await self.db.get(
            Customer, cid, options=[selectinload(Customer.preferred_tech)]
        )
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found")

        applied_priority, retention_flag = _apply_retention_priority(priority, churn_context)
        technician = await self._select_technician(customer)
        window_start, window_end = _parse_preferred_window(preferred_window)

        job_number = _generate_job_number()
        for _ in range(5):
            existing = await self.db.execute(
                select(DispatchJob).where(DispatchJob.job_number == job_number)
            )
            if existing.scalar_one_or_none() is None:
                break
            job_number = _generate_job_number()

        description = issue_description
        if access_instructions:
            description = f"{issue_description}\n\nAccess: {access_instructions}"

        job = DispatchJob(
            job_number=job_number,
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

    async def update_job(self, args: UpdateDispatchArgs) -> dict[str, Any]:
        job = await self.db.get(DispatchJob, uuid.UUID(args.job_id))
        if job is None:
            return {"success": False, "error": f"Dispatch job {args.job_id} not found"}

        changes: list[str] = []
        description = job.issue_description or ""

        if args.cancel:
            job.job_status = "CANCELLED"
            changes.append("booking cancelled")

        if args.preferred_window:
            window_start, window_end = _parse_preferred_window(args.preferred_window)
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

        summary = ", ".join(changes)
        return {
            "success": True,
            "job_id": str(job.job_id),
            "job_number": job.job_number,
            "job_status": job.job_status,
            "changes": changes,
            "message": f"Booking updated. {summary.capitalize()}.",
        }
