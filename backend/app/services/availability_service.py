from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import scoped
from app.models.dispatch_job import DispatchJob
from app.models.organization import Organization
from app.models.schedule_override import ScheduleOverride
from app.models.technician import Technician
from app.models.technician_schedule import TechnicianSchedule
from app.schemas.organization import OrganizationSettings
from app.schemas.scheduling import AvailableSlot
from app.services.window_parser import format_slot_label


def _parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return time(hour, minute)


def _time_ranges_overlap(
    start_a: time, end_a: time, start_b: time, end_b: time
) -> bool:
    return start_a < end_b and start_b < end_a


def _datetime_ranges_overlap(
    start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime
) -> bool:
    return start_a < end_b and start_b < end_a


class AvailabilityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_org_timezone(self, org_id: uuid.UUID) -> str:
        org = await self.db.get(Organization, org_id)
        if org is None:
            return "America/Los_Angeles"
        settings = OrganizationSettings.model_validate(org.settings or {})
        return settings.timezone

    async def _get_active_technicians(
        self,
        org_id: uuid.UUID,
        preferred_technician_id: uuid.UUID | None = None,
        required_skill: str | None = None,
    ) -> list[Technician]:
        stmt = scoped(
            select(Technician).where(Technician.employment_status == "ACTIVE"),
            Technician,
            org_id,
        )
        if preferred_technician_id:
            stmt = stmt.where(Technician.technician_id == preferred_technician_id)
        if required_skill is not None:
            stmt = stmt.where(Technician.skills.contains([required_skill]))
        return list((await self.db.execute(stmt.order_by(Technician.full_name))).scalars())

    async def _get_working_hours(
        self,
        org_id: uuid.UUID,
        technician_id: uuid.UUID,
        target_date: date,
    ) -> tuple[time, time] | None:
        override = (
            await self.db.execute(
                select(ScheduleOverride).where(
                    ScheduleOverride.org_id == org_id,
                    ScheduleOverride.technician_id == technician_id,
                    ScheduleOverride.override_date == target_date,
                )
            )
        ).scalar_one_or_none()

        if override:
            if override.override_type == "day_off":
                return None
            if override.override_type == "emergency_only":
                return None
            if override.override_type == "custom_hours":
                if override.start_time and override.end_time:
                    return override.start_time, override.end_time
                return None

        dow = target_date.weekday()
        schedule = (
            await self.db.execute(
                select(TechnicianSchedule).where(
                    TechnicianSchedule.org_id == org_id,
                    TechnicianSchedule.technician_id == technician_id,
                    TechnicianSchedule.day_of_week == dow,
                    TechnicianSchedule.is_active.is_(True),
                    TechnicianSchedule.effective_from <= target_date,
                    or_(
                        TechnicianSchedule.effective_until.is_(None),
                        TechnicianSchedule.effective_until >= target_date,
                    ),
                )
            )
        ).scalar_one_or_none()

        if schedule is None:
            return None
        return schedule.start_time, schedule.end_time

    async def _get_busy_blocks(
        self,
        org_id: uuid.UUID,
        technician_id: uuid.UUID,
        target_date: date,
        tz_name: str,
    ) -> list[tuple[time, time]]:
        tz = ZoneInfo(tz_name)
        day_start = datetime.combine(target_date, time.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)

        rows = (
            await self.db.execute(
                select(DispatchJob).where(
                    DispatchJob.org_id == org_id,
                    DispatchJob.technician_id == technician_id,
                    DispatchJob.scheduled_window_start.isnot(None),
                    DispatchJob.scheduled_window_end.isnot(None),
                    DispatchJob.scheduled_window_start < day_end,
                    DispatchJob.scheduled_window_end > day_start,
                    DispatchJob.job_status.notin_(("CANCELLED", "COMPLETED")),
                )
            )
        ).scalars().all()

        blocks: list[tuple[time, time]] = []
        for job in rows:
            assert job.scheduled_window_start is not None
            assert job.scheduled_window_end is not None
            start_local = job.scheduled_window_start.astimezone(tz)
            end_local = job.scheduled_window_end.astimezone(tz)
            blocks.append((start_local.time(), end_local.time()))
        return blocks

    def _generate_slots_for_day(
        self,
        target_date: date,
        work_start: time,
        work_end: time,
        busy_blocks: list[tuple[time, time]],
        technician: Technician,
        duration_minutes: int,
        tz_name: str,
        slot_increment_minutes: int = 120,
    ) -> list[AvailableSlot]:
        slots: list[AvailableSlot] = []
        cursor = datetime.combine(target_date, work_start)
        work_end_dt = datetime.combine(target_date, work_end)
        increment = timedelta(minutes=slot_increment_minutes)
        duration = timedelta(minutes=duration_minutes)

        while cursor + duration <= work_end_dt:
            slot_start = cursor.time()
            slot_end = (cursor + increment).time()
            if slot_end <= slot_start:
                break

            blocked = any(
                _time_ranges_overlap(slot_start, slot_end, busy[0], busy[1])
                for busy in busy_blocks
            )
            if not blocked:
                label = format_slot_label(target_date, slot_start, slot_end, tz_name)
                slots.append(
                    AvailableSlot(
                        date=target_date,
                        start_time=slot_start,
                        end_time=slot_end,
                        technician_id=technician.technician_id,
                        technician_name=technician.full_name,
                        slot_label=label,
                    )
                )
            cursor += increment
        return slots

    async def get_available_slots(
        self,
        org_id: uuid.UUID,
        date_range_start: date,
        date_range_end: date,
        duration_minutes: int = 60,
        preferred_technician_id: uuid.UUID | None = None,
        required_skill: str | None = None,
    ) -> list[AvailableSlot]:
        tz_name = await self._get_org_timezone(org_id)
        technicians = await self._get_active_technicians(
            org_id, preferred_technician_id, required_skill
        )
        if not technicians:
            return []

        all_slots: list[AvailableSlot] = []
        current = date_range_start
        max_end = min(date_range_end, date_range_start + timedelta(days=6))

        while current <= max_end:
            for tech in technicians:
                hours = await self._get_working_hours(org_id, tech.technician_id, current)
                if hours is None:
                    continue
                work_start, work_end = hours
                busy = await self._get_busy_blocks(
                    org_id, tech.technician_id, current, tz_name
                )
                all_slots.extend(
                    self._generate_slots_for_day(
                        current,
                        work_start,
                        work_end,
                        busy,
                        tech,
                        duration_minutes,
                        tz_name,
                    )
                )
            current += timedelta(days=1)

        all_slots.sort(key=lambda s: (s.date, s.start_time, s.technician_name))
        return all_slots[:10]

    async def check_slot_available(
        self,
        org_id: uuid.UUID,
        technician_id: uuid.UUID,
        slot_date: date,
        start_time: time,
        end_time: time,
    ) -> tuple[bool, str]:
        tech = await self.db.get(Technician, technician_id)
        if tech is None or tech.org_id != org_id:
            return False, "Technician not found for this organization."
        if tech.employment_status != "ACTIVE":
            return False, f"{tech.full_name} is not currently active."

        hours = await self._get_working_hours(org_id, technician_id, slot_date)
        if hours is None:
            return False, f"{tech.full_name} is not available on {slot_date.isoformat()}."
        work_start, work_end = hours
        if start_time < work_start or end_time > work_end:
            return False, (
                f"Requested window is outside {tech.full_name}'s working hours "
                f"({work_start.strftime('%H:%M')}–{work_end.strftime('%H:%M')})."
            )

        tz_name = await self._get_org_timezone(org_id)
        busy = await self._get_busy_blocks(org_id, technician_id, slot_date, tz_name)
        for busy_start, busy_end in busy:
            if _time_ranges_overlap(start_time, end_time, busy_start, busy_end):
                return False, (
                    f"{tech.full_name} already has a booking overlapping "
                    f"{start_time.strftime('%H:%M')}–{end_time.strftime('%H:%M')}."
                )

        return True, ""

    async def get_technician_schedule(
        self,
        org_id: uuid.UUID,
        technician_id: uuid.UUID,
        date_from: date,
        date_to: date,
    ) -> dict:
        tech = await self.db.get(Technician, technician_id)
        if tech is None or tech.org_id != org_id:
            return {"found": False}

        tz_name = await self._get_org_timezone(org_id)
        schedules = (
            await self.db.execute(
                scoped(
                    select(TechnicianSchedule).where(
                        TechnicianSchedule.technician_id == technician_id,
                        TechnicianSchedule.is_active.is_(True),
                    ),
                    TechnicianSchedule,
                    org_id,
                )
            )
        ).scalars().all()

        overrides = (
            await self.db.execute(
                scoped(
                    select(ScheduleOverride).where(
                        ScheduleOverride.technician_id == technician_id,
                        ScheduleOverride.override_date >= date_from,
                        ScheduleOverride.override_date <= date_to,
                    ),
                    ScheduleOverride,
                    org_id,
                )
            )
        ).scalars().all()

        tz = ZoneInfo(tz_name)
        range_start = datetime.combine(date_from, time.min, tzinfo=tz)
        range_end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)

        jobs = (
            await self.db.execute(
                select(DispatchJob).where(
                    DispatchJob.org_id == org_id,
                    DispatchJob.technician_id == technician_id,
                    DispatchJob.scheduled_window_start.isnot(None),
                    DispatchJob.scheduled_window_start >= range_start,
                    DispatchJob.scheduled_window_start < range_end,
                )
            )
        ).scalars().all()

        return {
            "found": True,
            "technician_id": str(technician_id),
            "technician_name": tech.full_name,
            "working_hours": [
                {
                    "day_of_week": row.day_of_week,
                    "start_time": row.start_time.isoformat(),
                    "end_time": row.end_time.isoformat(),
                }
                for row in schedules
            ],
            "overrides": [
                {
                    "override_date": row.override_date.isoformat(),
                    "override_type": row.override_type,
                    "start_time": row.start_time.isoformat() if row.start_time else None,
                    "end_time": row.end_time.isoformat() if row.end_time else None,
                    "reason": row.reason,
                }
                for row in overrides
            ],
            "booked_jobs": [
                {
                    "job_id": str(job.job_id),
                    "job_number": job.job_number,
                    "job_status": job.job_status,
                    "scheduled_window_start": job.scheduled_window_start.isoformat()
                    if job.scheduled_window_start
                    else None,
                    "scheduled_window_end": job.scheduled_window_end.isoformat()
                    if job.scheduled_window_end
                    else None,
                }
                for job in jobs
            ],
        }

    async def set_working_hours(
        self,
        org_id: uuid.UUID,
        technician_id: uuid.UUID,
        day_of_week: int,
        start_time: time,
        end_time: time,
    ) -> TechnicianSchedule:
        tech = await self.db.get(Technician, technician_id)
        if tech is None or tech.org_id != org_id:
            raise ValueError("Technician not found")

        existing = (
            await self.db.execute(
                select(TechnicianSchedule).where(
                    TechnicianSchedule.org_id == org_id,
                    TechnicianSchedule.technician_id == technician_id,
                    TechnicianSchedule.day_of_week == day_of_week,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.start_time = start_time
            existing.end_time = end_time
            existing.is_active = True
            await self.db.flush()
            return existing

        row = TechnicianSchedule(
            org_id=org_id,
            technician_id=technician_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            is_active=True,
            effective_from=date.today(),
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def add_override(
        self,
        org_id: uuid.UUID,
        technician_id: uuid.UUID,
        override_date: date,
        override_type: str,
        start_time: time | None = None,
        end_time: time | None = None,
        reason: str | None = None,
    ) -> ScheduleOverride:
        tech = await self.db.get(Technician, technician_id)
        if tech is None or tech.org_id != org_id:
            raise ValueError("Technician not found")

        existing = (
            await self.db.execute(
                select(ScheduleOverride).where(
                    ScheduleOverride.org_id == org_id,
                    ScheduleOverride.technician_id == technician_id,
                    ScheduleOverride.override_date == override_date,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.override_type = override_type
            existing.start_time = start_time
            existing.end_time = end_time
            existing.reason = reason
            await self.db.flush()
            return existing

        row = ScheduleOverride(
            org_id=org_id,
            technician_id=technician_id,
            override_date=override_date,
            override_type=override_type,
            start_time=start_time,
            end_time=end_time,
            reason=reason,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_scheduled_jobs(
        self,
        org_id: uuid.UUID,
        date_from: date,
        date_to: date,
        technician_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[dict]:
        tz_name = await self._get_org_timezone(org_id)
        tz = ZoneInfo(tz_name)
        range_start = datetime.combine(date_from, time.min, tzinfo=tz)
        range_end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)

        from app.models.customer import Customer

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
                DispatchJob.scheduled_window_start.isnot(None),
                DispatchJob.scheduled_window_start >= range_start,
                DispatchJob.scheduled_window_start < range_end,
            )
        )
        if technician_id:
            stmt = stmt.where(DispatchJob.technician_id == technician_id)
        if status:
            stmt = stmt.where(DispatchJob.job_status == status.upper())

        stmt = stmt.order_by(DispatchJob.scheduled_window_start.asc())
        rows = (await self.db.execute(stmt)).all()

        items: list[dict] = []
        for row in rows:
            items.append(
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
            )
        return items
