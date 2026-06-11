"""Unit tests for dispatch slot overlap detection."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.services.availability_service import (
    AvailabilityService,
    _datetime_ranges_overlap,
    _time_ranges_overlap,
)

TZ = ZoneInfo("America/Los_Angeles")


@pytest.mark.parametrize(
    "start_a,end_a,start_b,end_b,expected",
    [
        (time(8, 0), time(10, 0), time(10, 0), time(12, 0), False),
        (time(9, 0), time(11, 0), time(8, 0), time(10, 0), True),
        (time(8, 0), time(10, 0), time(8, 0), time(10, 0), True),
        (time(8, 30), time(9, 30), time(8, 0), time(10, 0), True),
    ],
)
def test_time_ranges_overlap_cases(start_a, end_a, start_b, end_b, expected):
    assert _time_ranges_overlap(start_a, end_a, start_b, end_b) is expected


def test_datetime_ranges_overlap_adjacent_no_conflict():
    day = date(2026, 6, 10)
    a_start = datetime.combine(day, time(8, 0), tzinfo=TZ)
    a_end = datetime.combine(day, time(10, 0), tzinfo=TZ)
    b_start = datetime.combine(day, time(10, 0), tzinfo=TZ)
    b_end = datetime.combine(day, time(12, 0), tzinfo=TZ)
    assert _datetime_ranges_overlap(a_start, a_end, b_start, b_end) is False


@pytest.mark.asyncio
async def test_check_slot_available_excludes_current_job(db_session, seeded_customer):
    from app.core.constants import SEED_ORG_ID
    from app.models.dispatch_job import DispatchJob
    from app.services.availability_service import AvailabilityService
    from tests.test_availability_service import _seed_tech_with_hours

    tech = await _seed_tech_with_hours(db_session, "Reschedule Tech")
    slot_date = date(2026, 6, 16)
    window_start = datetime.combine(slot_date, time(8, 0), tzinfo=TZ)
    window_end = datetime.combine(slot_date, time(10, 0), tzinfo=TZ)
    job = DispatchJob(
        job_number="DX-EXCLUDE-001",
        org_id=SEED_ORG_ID,
        customer_id=uuid.UUID(seeded_customer["customer_id"]),
        technician_id=tech.technician_id,
        job_status="SCHEDULED",
        priority="P3",
        issue_type="AC_FAILURE",
        scheduled_window_start=window_start,
        scheduled_window_end=window_end,
    )
    db_session.add(job)
    await db_session.flush()

    service = AvailabilityService(db_session)
    ok, _ = await service.check_slot_available(
        SEED_ORG_ID,
        tech.technician_id,
        slot_date,
        time(8, 0),
        time(10, 0),
        exclude_job_id=job.job_id,
    )
    assert ok is True
