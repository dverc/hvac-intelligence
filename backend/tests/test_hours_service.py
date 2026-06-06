from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.services.hours_service import get_hours_context, is_within_business_hours

_SETTINGS = {
    "timezone": "America/Los_Angeles",
    "business_hours": {
        "monday": {"open": "08:00", "close": "17:00"},
        "tuesday": {"open": "08:00", "close": "17:00"},
        "wednesday": {"open": "08:00", "close": "17:00"},
        "thursday": {"open": "08:00", "close": "17:00"},
        "friday": {"open": "08:00", "close": "17:00"},
        "saturday": None,
        "sunday": None,
    },
}


def _freeze(moment: datetime):
    tz_name = str(moment.tzinfo)
    return patch(
        "app.services.hours_service._now_in_timezone",
        return_value=moment,
    )


def test_is_within_business_hours_returns_true_during_configured_hours():
    moment = datetime(2026, 1, 7, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    with _freeze(moment):
        assert is_within_business_hours(_SETTINGS) is True


def test_is_within_business_hours_returns_false_on_sunday():
    moment = datetime(2026, 1, 4, 12, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    with _freeze(moment):
        assert is_within_business_hours(_SETTINGS) is False


def test_is_within_business_hours_returns_false_at_2am_on_weekday():
    moment = datetime(2026, 1, 7, 2, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    with _freeze(moment):
        assert is_within_business_hours(_SETTINGS) is False


def test_is_within_business_hours_uses_default_hours_when_missing_key():
    moment = datetime(2026, 1, 7, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    with _freeze(moment):
        assert is_within_business_hours({}) is True


def test_get_hours_context_returns_correct_string_when_open():
    moment = datetime(2026, 1, 7, 10, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    with _freeze(moment):
        assert get_hours_context(_SETTINGS) == "Currently within business hours."


def test_get_hours_context_returns_next_opening_when_closed():
    moment = datetime(2026, 1, 4, 12, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    with _freeze(moment):
        context = get_hours_context(_SETTINGS)
    assert context.startswith("Currently outside business hours.")
    assert "Next opening: Monday at 08:00" in context
