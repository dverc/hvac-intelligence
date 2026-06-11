from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import update

from app.core.constants import SEED_ORG_ID
from app.models.dispatch_job import DispatchJob
from app.models.technician_schedule import TechnicianSchedule
from app.services.dispatch_service import DispatchService
from app.services.window_parser import parse_preferred_window


@pytest.mark.parametrize(
    ("window", "expected_start", "expected_end"),
    [
        ("tomorrow 2 to 4 PM", time(14, 0), time(16, 0)),
        ("Wednesday June 10 2-4 PM", time(14, 0), time(16, 0)),
        ("10 AM to noon", time(10, 0), time(12, 0)),
        (
            "Tomorrow Monday June 8 10 AM to 12 PM with Elena",
            time(10, 0),
            time(12, 0),
        ),
        ("Monday, June 10 — 12:00 PM–2:00 PM", time(12, 0), time(14, 0)),
    ],
)
def test_parse_preferred_window_explicit_times(window, expected_start, expected_end):
    fixed_today = date(2026, 6, 9)
    with patch(
        "app.services.window_parser._today_in_tz",
        return_value=fixed_today,
    ):
        parsed = parse_preferred_window(window, "America/Los_Angeles")

    assert parsed.times_resolved is True
    assert parsed.start_time == expected_start
    assert parsed.end_time == expected_end


def test_parse_preferred_window_tomorrow_without_time_is_unresolved():
    fixed_today = date(2026, 6, 9)
    with patch(
        "app.services.window_parser._today_in_tz",
        return_value=fixed_today,
    ):
        parsed = parse_preferred_window("tomorrow", "America/Los_Angeles")

    assert parsed.times_resolved is False
    assert parsed.slot_date == date(2026, 6, 10)


def test_tomorrow_2_to_4_pm_converts_to_utc_during_pdt():
    """14:00-16:00 LA on a summer day → 21:00-23:00 UTC (PDT, UTC-7)."""
    fixed_today = date(2026, 6, 9)
    tz_name = "America/Los_Angeles"
    with patch(
        "app.services.window_parser._today_in_tz",
        return_value=fixed_today,
    ):
        parsed = parse_preferred_window("tomorrow 2 to 4 PM", tz_name)

    start_local, end_local = parsed.to_datetimes(tz_name)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    assert parsed.slot_date == date(2026, 6, 10)
    assert start_local.hour == 14 and start_local.minute == 0
    assert end_local.hour == 16 and end_local.minute == 0
    assert start_utc == datetime(2026, 6, 10, 21, 0, tzinfo=timezone.utc)
    assert end_utc == datetime(2026, 6, 10, 23, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_create_job_stores_requested_window_in_utc(
    db_session, seeded_customer
):
    fixed_today = date(2026, 6, 9)
    tz_name = "America/Los_Angeles"
    await db_session.execute(
        update(TechnicianSchedule)
        .where(
            TechnicianSchedule.technician_id
            == uuid.UUID(seeded_customer["technician_id"])
        )
        .values(effective_from=fixed_today)
    )
    await db_session.flush()
    with patch(
        "app.services.window_parser._today_in_tz",
        return_value=fixed_today,
    ):
        svc = DispatchService(db_session)
        result = await svc.create_job(
            customer_id=seeded_customer["customer_id"],
            issue_type="AC_FAILURE",
            priority="P2",
            preferred_window="tomorrow 2 to 4 PM",
            issue_description="Afternoon service",
            org_id=SEED_ORG_ID,
        )

    assert result["success"] is True, result
    job = await db_session.get(DispatchJob, uuid.UUID(result["job_id"]))
    assert job is not None
    start_utc = job.scheduled_window_start
    end_utc = job.scheduled_window_end
    la = ZoneInfo(tz_name)
    assert start_utc.astimezone(la).time() == time(14, 0)
    assert end_utc.astimezone(la).time() == time(16, 0)
    assert start_utc.astimezone(timezone.utc) == datetime(
        2026, 6, 10, 21, 0, tzinfo=timezone.utc
    )
    assert end_utc.astimezone(timezone.utc) == datetime(
        2026, 6, 10, 23, 0, tzinfo=timezone.utc
    )
