"""Business-hours helpers for after-hours call handling."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

_DEFAULT_TIMEZONE = "America/Los_Angeles"
_DEFAULT_BUSINESS_HOURS: dict[str, dict[str, str] | None] = {
    "monday": {"open": "08:00", "close": "17:00"},
    "tuesday": {"open": "08:00", "close": "17:00"},
    "wednesday": {"open": "08:00", "close": "17:00"},
    "thursday": {"open": "08:00", "close": "17:00"},
    "friday": {"open": "08:00", "close": "17:00"},
    "saturday": None,
    "sunday": None,
}
_DAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return time(hour, minute)


def _resolve_hours_and_timezone(settings: dict) -> tuple[dict[str, dict[str, str] | None], str]:
    tz_name = settings.get("timezone") or _DEFAULT_TIMEZONE
    business_hours = settings.get("business_hours")
    if not business_hours:
        business_hours = _DEFAULT_BUSINESS_HOURS
    return business_hours, tz_name


def _now_in_timezone(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def _day_name(weekday: int) -> str:
    return _DAY_NAMES[weekday]


def _is_open_at(
    business_hours: dict[str, dict[str, str] | None],
    moment: datetime,
) -> bool:
    day_hours = business_hours.get(_day_name(moment.weekday()))
    if not day_hours:
        return False
    open_time = _parse_hhmm(day_hours["open"])
    close_time = _parse_hhmm(day_hours["close"])
    current = moment.time()
    return open_time <= current < close_time


def _find_next_opening(
    business_hours: dict[str, dict[str, str] | None],
    moment: datetime,
) -> tuple[str, time, str]:
    tz_abbr = moment.tzname() or ""
    for offset in range(8):
        candidate = moment + timedelta(days=offset)
        day_hours = business_hours.get(_day_name(candidate.weekday()))
        if not day_hours:
            continue
        open_time = _parse_hhmm(day_hours["open"])
        close_time = _parse_hhmm(day_hours["close"])
        if offset == 0:
            if candidate.time() < open_time:
                return _day_name(candidate.weekday()).capitalize(), open_time, tz_abbr
            if candidate.time() >= close_time:
                continue
            continue
        return _day_name(candidate.weekday()).capitalize(), open_time, tz_abbr
    return "Monday", time(8, 0), tz_abbr


def _format_time(value: time) -> str:
    return value.strftime("%H:%M")


def is_within_business_hours(settings: dict) -> bool:
    """Return True when the current local time is inside configured business hours."""
    business_hours, tz_name = _resolve_hours_and_timezone(settings)
    now = _now_in_timezone(tz_name)
    return _is_open_at(business_hours, now)


def get_hours_context(settings: dict) -> str:
    """Return a short description of the current business-hours status."""
    business_hours, tz_name = _resolve_hours_and_timezone(settings)
    now = _now_in_timezone(tz_name)
    if _is_open_at(business_hours, now):
        return "Currently within business hours."
    day_name, open_time, tz_abbr = _find_next_opening(business_hours, now)
    return (
        "Currently outside business hours. "
        f"Next opening: {day_name} at {_format_time(open_time)} {tz_abbr}."
    )
