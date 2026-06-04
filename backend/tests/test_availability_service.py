import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.constants import SEED_ORG_ID
from app.models.dispatch_job import DispatchJob
from app.models.technician import Technician
from app.models.technician_schedule import TechnicianSchedule
from app.services.availability_service import AvailabilityService


async def _seed_tech_with_hours(db_session, name: str = "Avail Tech") -> Technician:
    tech = Technician(
        org_id=SEED_ORG_ID,
        employee_number=f"T-AVAIL-{uuid.uuid4().hex[:6]}",
        full_name=name,
        hire_date=date(2019, 1, 1),
        employment_status="ACTIVE",
    )
    db_session.add(tech)
    await db_session.flush()
    for dow in range(5):
        db_session.add(
            TechnicianSchedule(
                org_id=SEED_ORG_ID,
                technician_id=tech.technician_id,
                day_of_week=dow,
                start_time=time(8, 0),
                end_time=time(17, 0),
                is_active=True,
                effective_from=date.today(),
            )
        )
    await db_session.flush()
    return tech


def _next_weekday(weekday: int) -> date:
    today = date.today()
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


@pytest.fixture
def availability_service(db_session):
    return AvailabilityService(db_session)


@pytest.mark.asyncio
async def test_get_available_slots_weekday_hours(availability_service, db_session):
    await _seed_tech_with_hours(db_session)
    await db_session.commit()

    target = _next_weekday(0)
    slots = await availability_service.get_available_slots(
        SEED_ORG_ID, target, target, duration_minutes=60
    )
    assert len(slots) >= 1
    assert all(s.date == target for s in slots)


@pytest.mark.asyncio
async def test_get_available_slots_excludes_booked_job(availability_service, db_session):
    from app.models.customer import Customer

    tech = await _seed_tech_with_hours(db_session)
    customer = Customer(
        org_id=SEED_ORG_ID,
        full_name="Slot Block Customer",
        phone_primary=f"+1555{uuid.uuid4().int % 10000000:07d}",
        customer_since=date(2020, 1, 1),
    )
    db_session.add(customer)
    await db_session.flush()

    target = _next_weekday(0)
    tz = ZoneInfo("America/Los_Angeles")
    block_start = datetime.combine(target, time(8, 0), tzinfo=tz)
    block_end = datetime.combine(target, time(10, 0), tzinfo=tz)
    db_session.add(
        DispatchJob(
            job_number=f"DX-BLOCK-{uuid.uuid4().hex[:4]}",
            org_id=SEED_ORG_ID,
            customer_id=customer.customer_id,
            technician_id=tech.technician_id,
            issue_type="AC_FAILURE",
            priority="P2",
            job_status="SCHEDULED",
            scheduled_window_start=block_start,
            scheduled_window_end=block_end,
        )
    )
    await db_session.commit()

    slots = await availability_service.get_available_slots(
        SEED_ORG_ID, target, target, duration_minutes=60
    )
    tech_slots = [s for s in slots if s.technician_id == tech.technician_id]
    assert not any(s.start_time == time(8, 0) and s.end_time == time(10, 0) for s in tech_slots)


@pytest.mark.asyncio
async def test_day_off_override_excludes_slots(availability_service, db_session):
    tech = await _seed_tech_with_hours(db_session)
    target = _next_weekday(1)
    await availability_service.add_override(
        SEED_ORG_ID, tech.technician_id, target, "day_off", reason="PTO"
    )
    await db_session.commit()

    slots = await availability_service.get_available_slots(
        SEED_ORG_ID, target, target, preferred_technician_id=tech.technician_id
    )
    assert slots == []


@pytest.mark.asyncio
async def test_custom_hours_override(availability_service, db_session):
    tech = await _seed_tech_with_hours(db_session)
    target = _next_weekday(2)
    await availability_service.add_override(
        SEED_ORG_ID,
        tech.technician_id,
        target,
        "custom_hours",
        start_time=time(10, 0),
        end_time=time(12, 0),
    )
    await db_session.commit()

    slots = await availability_service.get_available_slots(
        SEED_ORG_ID,
        target,
        target,
        duration_minutes=60,
        preferred_technician_id=tech.technician_id,
    )
    assert slots
    assert all(s.start_time >= time(10, 0) for s in slots)


@pytest.mark.asyncio
async def test_check_slot_available_free_window(availability_service, db_session):
    tech = await _seed_tech_with_hours(db_session)
    await db_session.commit()
    target = _next_weekday(3)
    ok, reason = await availability_service.check_slot_available(
        SEED_ORG_ID, tech.technician_id, target, time(8, 0), time(10, 0)
    )
    assert ok is True
    assert reason == ""


@pytest.mark.asyncio
async def test_check_slot_available_conflicting_job(availability_service, db_session):
    from app.models.customer import Customer

    tech = await _seed_tech_with_hours(db_session)
    customer = Customer(
        org_id=SEED_ORG_ID,
        full_name="Conflict Customer",
        phone_primary=f"+1555{uuid.uuid4().int % 10000000:07d}",
        customer_since=date(2020, 1, 1),
    )
    db_session.add(customer)
    await db_session.flush()

    target = _next_weekday(4)
    tz = ZoneInfo("America/Los_Angeles")
    db_session.add(
        DispatchJob(
            job_number=f"DX-CONF-{uuid.uuid4().hex[:4]}",
            org_id=SEED_ORG_ID,
            customer_id=customer.customer_id,
            technician_id=tech.technician_id,
            issue_type="AC_FAILURE",
            priority="P2",
            job_status="SCHEDULED",
            scheduled_window_start=datetime.combine(target, time(8, 0), tzinfo=tz),
            scheduled_window_end=datetime.combine(target, time(10, 0), tzinfo=tz),
        )
    )
    await db_session.commit()

    ok, reason = await availability_service.check_slot_available(
        SEED_ORG_ID, tech.technician_id, target, time(8, 0), time(10, 0)
    )
    assert ok is False
    assert "booking" in reason.lower() or "overlapping" in reason.lower()


@pytest.mark.asyncio
async def test_check_slot_available_outside_working_hours(
    availability_service, db_session
):
    tech = await _seed_tech_with_hours(db_session)
    await db_session.commit()
    target = _next_weekday(0)
    ok, reason = await availability_service.check_slot_available(
        SEED_ORG_ID, tech.technician_id, target, time(6, 0), time(7, 0)
    )
    assert ok is False
    assert "working hours" in reason.lower()
