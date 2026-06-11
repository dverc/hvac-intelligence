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

_MONTH_NAMES = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_TIME_RANGE_PATTERNS: list[re.Pattern[str]] = [
    # 10 am to 12 pm / 10 am to noon
    re.compile(
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s+(?:to|–|—|-)\s+"
        r"(\d{1,2}|noon|midnight)(?::(\d{2}))?\s*(am|pm)?",
        re.IGNORECASE,
    ),
    # 2 to 4 pm / 2-4 pm (meridiem on end only)
    re.compile(
        r"(\d{1,2})(?::(\d{2}))?\s*(?:to|–|—|-)\s*"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
        re.IGNORECASE,
    ),
    # 12:00 pm–2:00 pm (slot labels from format_slot_label)
    re.compile(
        r"(\d{1,2}):(\d{2})\s*(am|pm)\s*[–—]\s*"
        r"(\d{1,2}):(\d{2})\s*(am|pm)",
        re.IGNORECASE,
    ),
    # 14:00-16:00
    re.compile(
        r"\b(\d{1,2}):(\d{2})\s*(?:to|–|—|-)\s*(\d{1,2}):(\d{2})\b",
        re.IGNORECASE,
    ),
]


@dataclass(frozen=True)
class ParsedWindow:
    slot_date: date
    start_time: time
    end_time: time
    times_resolved: bool = True

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


def _apply_meridiem(hour: int, meridiem: str | None) -> int:
    mer = (meridiem or "").lower()
    if mer == "pm" and hour < 12:
        return hour + 12
    if mer == "am" and hour == 12:
        return 0
    return hour


def _parse_clock_token(
    token: str, minute: int, meridiem: str | None
) -> time | None:
    token_lower = token.lower()
    if token_lower == "noon":
        return time(12, 0)
    if token_lower == "midnight":
        return time(0, 0)
    try:
        hour = int(token)
    except ValueError:
        return None
    if hour > 23:
        return None
    if meridiem and meridiem.lower() in {"am", "pm"}:
        hour = _apply_meridiem(hour, meridiem)
    return time(hour, minute)


def _parse_time_range(lower: str) -> tuple[time, time] | None:
    # 10 am to 12 pm / 10 am to noon
    match = _TIME_RANGE_PATTERNS[0].search(lower)
    if match:
        start_hour_s, start_min_s, start_mer, end_hour_s, end_min_s, end_mer = (
            match.groups()
        )
        start_min = int(start_min_s) if start_min_s else 0
        end_min = int(end_min_s) if end_min_s else 0
        end_mer = end_mer or start_mer
        start_t = _parse_clock_token(start_hour_s, start_min, start_mer)
        end_t = _parse_clock_token(end_hour_s, end_min, end_mer)
        if start_t and end_t and start_t < end_t:
            return start_t, end_t

    # 2 to 4 pm / 2-4 pm
    match = _TIME_RANGE_PATTERNS[1].search(lower)
    if match:
        start_hour_s, start_min_s, end_hour_s, end_min_s, end_mer = match.groups()
        start_min = int(start_min_s) if start_min_s else 0
        end_min = int(end_min_s) if end_min_s else 0
        start_t = _parse_clock_token(start_hour_s, start_min, end_mer)
        end_t = _parse_clock_token(end_hour_s, end_min, end_mer)
        if start_t and end_t and start_t < end_t:
            return start_t, end_t

    # 12:00 pm–2:00 pm
    match = _TIME_RANGE_PATTERNS[2].search(lower)
    if match:
        sh, sm, smer, eh, em, emer = match.groups()
        start_t = _parse_clock_token(sh, int(sm), smer)
        end_t = _parse_clock_token(eh, int(em), emer)
        if start_t and end_t and start_t < end_t:
            return start_t, end_t

    # 14:00-16:00
    match = _TIME_RANGE_PATTERNS[3].search(lower)
    if match:
        sh, sm, eh, em = match.groups()
        try:
            start_t = time(int(sh), int(sm))
            end_t = time(int(eh), int(em))
        except ValueError:
            return None
        if start_t < end_t:
            return start_t, end_t

    return None


def _parse_month_day(lower: str, today: date) -> date | None:
    match = re.search(
        r"\b("
        r"january|february|march|april|may|june|july|august|"
        r"september|october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
        r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        lower,
    )
    if not match:
        return None
    month = _MONTH_NAMES[match.group(1)]
    day = int(match.group(2))
    year = today.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    if candidate < today:
        candidate = date(year + 1, month, day)
    return candidate


def _parse_date(lower: str, today: date) -> date:
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", lower)
    if iso:
        return date.fromisoformat(iso.group(1))

    month_day = _parse_month_day(lower, today)
    if month_day is not None:
        return month_day

    for name, weekday in _DAY_NAMES.items():
        if re.search(rf"\b{re.escape(name)}\b", lower):
            return _next_weekday(today, weekday)

    if re.search(r"\btomorrow\b", lower) or "next day" in lower:
        return today + timedelta(days=1)
    if re.search(r"\btoday\b", lower) or "same day" in lower:
        return today

    return today + timedelta(days=3)


def parse_preferred_window(
    preferred_window: str | None,
    tz_name: str = "America/Los_Angeles",
) -> ParsedWindow:
    """Map natural-language booking windows to date + local times."""
    today = _today_in_tz(tz_name)
    if not preferred_window or not str(preferred_window).strip():
        return ParsedWindow(
            slot_date=today + timedelta(days=3),
            start_time=time(8, 0),
            end_time=time(10, 0),
            times_resolved=False,
        )
    lower = preferred_window.lower().strip()

    slot_date = _parse_date(lower, today)
    times_resolved = False
    start_t = time(8, 0)
    end_t = time(10, 0)

    explicit = _parse_time_range(lower)
    if explicit is not None:
        start_t, end_t = explicit
        times_resolved = True
    elif "afternoon" in lower:
        start_t, end_t = time(13, 0), time(15, 0)
        times_resolved = True
    elif "evening" in lower:
        start_t, end_t = time(15, 0), time(17, 0)
        times_resolved = True
    elif "morning" in lower:
        start_t, end_t = time(8, 0), time(10, 0)
        times_resolved = True

    return ParsedWindow(
        slot_date=slot_date,
        start_time=start_t,
        end_time=end_t,
        times_resolved=times_resolved,
    )


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
