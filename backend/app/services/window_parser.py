"""Natural-language and structured date/window parsing (stdlib only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class ParsedWindow:
    slot_date: date
    start_time: time
    end_time: time

    def to_datetimes(self, tz_name: str) -> tuple[datetime, datetime]:
        tz = ZoneInfo(tz_name)
        start = datetime.combine(self.slot_date, self.start_time, tzinfo=tz)
        end = datetime.combine(self.slot_date, self.end_time, tzinfo=tz)
        return start, end


def _today_in_tz(tz_name: str) -> date:
    return datetime.now(ZoneInfo(tz_name)).date()


def _next_weekday(from_date: date, weekday: int) -> date:
    days_ahead = (weekday - from_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return from_date + timedelta(days=days_ahead)


def parse_preferred_window(
    preferred_window: str,
    tz_name: str = "America/Los_Angeles",
) -> ParsedWindow:
    """Map natural-language booking windows to date + local times."""
    today = _today_in_tz(tz_name)
    lower = preferred_window.lower().strip()

    slot_date = today + timedelta(days=3)
    start_t = time(8, 0)
    end_t = time(10, 0)

    for name, weekday in _DAY_NAMES.items():
        if name in lower:
            slot_date = _next_weekday(today, weekday)
            break
    else:
        if "tomorrow" in lower or "next day" in lower:
            slot_date = today + timedelta(days=1)
        elif "today" in lower or "same day" in lower:
            slot_date = today

    if "afternoon" in lower:
        start_t, end_t = time(13, 0), time(15, 0)
    elif "evening" in lower:
        start_t, end_t = time(15, 0), time(17, 0)
    elif "morning" in lower or "tomorrow" in lower or "today" in lower:
        start_t, end_t = time(8, 0), time(10, 0)

    return ParsedWindow(slot_date=slot_date, start_time=start_t, end_time=end_t)


def parse_date_range(
    preferred_date: str | None,
    num_days: int,
    tz_name: str = "America/Los_Angeles",
) -> tuple[date, date]:
    """Parse preferred_date into an inclusive date range (max 7 days span)."""
    today = _today_in_tz(tz_name)
    num_days = max(1, min(num_days, 7))

    if not preferred_date or not preferred_date.strip():
        start = today + timedelta(days=1)
        end = start + timedelta(days=num_days - 1)
        return start, end

    text = preferred_date.strip().lower()

    if text == "today":
        start = today
    elif text == "tomorrow":
        start = today + timedelta(days=1)
    elif text == "this week":
        start = today
        end = min(today + timedelta(days=6), today + timedelta(days=num_days - 1))
        return start, end
    elif text == "next week":
        start = _next_weekday(today, 0)
        end = start + timedelta(days=min(6, num_days - 1))
        return start, end
    elif text in _DAY_NAMES:
        start = _next_weekday(today, _DAY_NAMES[text])
    elif re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        start = date.fromisoformat(text)
    else:
        start = today + timedelta(days=1)

    end = start + timedelta(days=num_days - 1)
    if (end - start).days > 6:
        end = start + timedelta(days=6)
    return start, end


def format_slot_label(
    slot_date: date,
    start_time: time,
    end_time: time,
    tz_name: str = "America/Los_Angeles",
) -> str:
    today = _today_in_tz(tz_name)
    tomorrow = today + timedelta(days=1)
    day_part = f"{slot_date.strftime('%A, %B')} {slot_date.day}"
    if slot_date == today:
        prefix = "Today"
    elif slot_date == tomorrow:
        prefix = "Tomorrow"
    else:
        prefix = day_part

    def fmt(t: time) -> str:
        hour = t.hour % 12 or 12
        minute = f":{t.minute:02d}" if t.minute else ""
        suffix = "AM" if t.hour < 12 else "PM"
        return f"{hour}{minute} {suffix}"

    return f"{prefix}, {day_part} — {fmt(start_time)}–{fmt(end_time)}"
