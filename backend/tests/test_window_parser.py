"""Unit tests for natural-language booking window parsing."""

from __future__ import annotations

from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.window_parser import (
    ParsedWindow,
    format_slot_label,
    parse_date_range,
    parse_preferred_window,
)

TZ = "America/Los_Angeles"


def _today() -> date:
    from datetime import datetime

    return datetime.now(ZoneInfo(TZ)).date()


@pytest.mark.parametrize(
    "window,expected_start,expected_end",
    [
        ("2 to 4 PM", time(14, 0), time(16, 0)),
        ("2-4 PM", time(14, 0), time(16, 0)),
        ("10 AM to noon", time(10, 0), time(12, 0)),
        ("14:00-16:00", time(14, 0), time(16, 0)),
    ],
)
def test_parse_explicit_time_ranges(window, expected_start, expected_end):
    parsed = parse_preferred_window(f"tomorrow {window}", TZ)
    assert parsed.times_resolved is True
    assert parsed.start_time == expected_start
    assert parsed.end_time == expected_end


@pytest.mark.parametrize(
    "window,expected_start,expected_end",
    [
        ("morning", time(8, 0), time(10, 0)),
        ("afternoon", time(13, 0), time(15, 0)),
        ("evening", time(15, 0), time(17, 0)),
    ],
)
def test_parse_semantic_dayparts(window, expected_start, expected_end):
    parsed = parse_preferred_window(f"tomorrow {window}", TZ)
    assert parsed.times_resolved is True
    assert parsed.start_time == expected_start
    assert parsed.end_time == expected_end


@pytest.mark.parametrize("window", [None, "", "   "])
def test_parse_null_or_empty_window_returns_unresolved(window):
    parsed = parse_preferred_window(window, TZ)
    assert parsed.times_resolved is False
    assert parsed.start_time == time(8, 0)
    assert parsed.end_time == time(10, 0)


def test_parse_unrecognized_format_defaults_unresolved():
    parsed = parse_preferred_window("tomorrow sometime soon maybe", TZ)
    assert parsed.times_resolved is False


def test_parse_iso_date_in_window():
    parsed = parse_preferred_window("2026-06-10 2 to 4 PM", TZ)
    assert parsed.slot_date == date(2026, 6, 10)
    assert parsed.times_resolved is True


def test_to_datetimes_uses_org_timezone():
    parsed = ParsedWindow(
        slot_date=date(2026, 6, 10),
        start_time=time(14, 0),
        end_time=time(16, 0),
    )
    start, end = parsed.to_datetimes(TZ)
    assert start.tzinfo == ZoneInfo(TZ)
    assert start.hour == 14
    assert end.hour == 16


def test_parse_date_range_defaults_to_tomorrow():
    start, end = parse_date_range(None, 3, TZ)
    today = _today()
    assert start == today + timedelta(days=1)


def test_format_slot_label_includes_times():
    label = format_slot_label(date(2026, 6, 10), time(14, 0), time(16, 0), TZ)
    assert "2:00 PM" in label or "2 PM" in label
    assert "–" in label or "-" in label
