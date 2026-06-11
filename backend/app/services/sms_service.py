"""Outbound SMS via Twilio."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.dispatch_job import DispatchJob

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "America/Los_Angeles"

_ISSUE_TYPE_FRIENDLY: dict[str, str] = {
    "AC_NO_COOLING": "AC not cooling",
    "AC_NO_HEAT": "heating",
    "HVAC_MAINTENANCE": "maintenance",
    "ELECTRICAL_ISSUE": "electrical",
    "PLUMBING_ISSUE": "plumbing",
}


def issue_type_friendly(issue_type: str | None) -> str:
    if not issue_type:
        return "service"
    return _ISSUE_TYPE_FRIENDLY.get(issue_type.upper(), "service")


def normalize_phone_to_e164(to_number: str) -> str:
    """Normalize a phone number to E.164 (+1XXXXXXXXXX for US 10-digit numbers)."""
    raw = (to_number or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if raw.startswith("+"):
        return f"+{digits}"
    return f"+{digits}"


def _format_date_local(dt: datetime, tz_name: str) -> str:
    local = _to_local(dt, tz_name)
    return f"{local.strftime('%A')}, {local.strftime('%B')} {local.day}"


def _format_time_local(dt: datetime, tz_name: str) -> str:
    local = _to_local(dt, tz_name)
    return local.strftime("%I:%M %p")


def _to_local(dt: datetime, tz_name: str) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz_name))


def _customer_first_name(customer: Customer) -> str:
    name = (customer.full_name or "").strip()
    return name.split()[0] if name else "there"


def _window_times(
    job: DispatchJob,
    tz_name: str,
) -> tuple[str, str, str]:
    """Return (date_label, start_time, end_time) in the org timezone."""
    if job.scheduled_window_start is None:
        return "your scheduled date", "your scheduled time", "your scheduled time"
    date_label = _format_date_local(job.scheduled_window_start, tz_name)
    start_time = _format_time_local(job.scheduled_window_start, tz_name)
    if job.scheduled_window_end is not None:
        end_time = _format_time_local(job.scheduled_window_end, tz_name)
    else:
        end_time = start_time
    return date_label, start_time, end_time


def send_sms(to_number: str, message: str) -> bool:
    """Send an SMS via Twilio. Returns False when unconfigured or on failure."""
    settings = get_settings()
    if (
        not settings.TWILIO_ACCOUNT_SID
        or not settings.TWILIO_AUTH_TOKEN
        or not settings.TWILIO_FROM_NUMBER
    ):
        logger.warning("Twilio not configured — SMS not sent")
        return False

    normalized = normalize_phone_to_e164(to_number)
    if not normalized:
        logger.warning("SMS not sent — invalid or empty phone number")
        return False
    try:
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        result = client.messages.create(
            body=message,
            from_=settings.TWILIO_FROM_NUMBER,
            to=normalized,
        )
        logger.info("SMS sent to %s, sid=%s", normalized, result.sid)
        return True
    except Exception:
        logger.exception("Failed to send SMS to %s", normalized)
        return False


class SmsService:
    """High-level SMS helpers for dispatch notifications."""

    def send_booking_confirmation(
        self,
        job: DispatchJob,
        customer: Customer,
        *,
        technician_name: str = "our technician",
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> bool:
        if not customer.phone_primary:
            logger.warning(
                "send_booking_confirmation: no phone for customer %s",
                customer.customer_id,
            )
            return False

        date_label, start_time, end_time = _window_times(job, timezone_name)
        message = (
            f"Hi {_customer_first_name(customer)}! Your "
            f"{issue_type_friendly(job.issue_type)} appointment is confirmed for "
            f"{date_label} between {start_time} and {end_time}. "
            f"Your technician will be {technician_name}. Reply STOP to opt out."
        )
        return send_sms(customer.phone_primary, message)

    def send_24h_reminder(
        self,
        job: DispatchJob,
        customer: Customer,
        *,
        technician_name: str = "our technician",
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> bool:
        if not customer.phone_primary:
            logger.warning(
                "send_24h_reminder: no phone for customer %s",
                customer.customer_id,
            )
            return False

        date_label, start_time, end_time = _window_times(job, timezone_name)
        message = (
            f"Reminder: Your HVAC appointment is tomorrow {date_label} between "
            f"{start_time} and {end_time} with {technician_name}. "
            "Reply STOP to opt out."
        )
        return send_sms(customer.phone_primary, message)

    def send_1h_reminder(
        self,
        job: DispatchJob,
        customer: Customer,
        *,
        technician_name: str = "our technician",
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> bool:
        if not customer.phone_primary:
            logger.warning(
                "send_1h_reminder: no phone for customer %s",
                customer.customer_id,
            )
            return False

        _, start_time, end_time = _window_times(job, timezone_name)
        message = (
            f"Your HVAC technician {technician_name} is on their way and will arrive "
            f"between {start_time} and {end_time} today. Reply STOP to opt out."
        )
        return send_sms(customer.phone_primary, message)


# Module-level convenience aliases
def send_booking_confirmation(
    job: DispatchJob,
    customer: Customer,
    *,
    technician_name: str = "our technician",
    timezone_name: str = DEFAULT_TIMEZONE,
) -> bool:
    return SmsService().send_booking_confirmation(
        job,
        customer,
        technician_name=technician_name,
        timezone_name=timezone_name,
    )


def send_24h_reminder(
    job: DispatchJob,
    customer: Customer,
    *,
    technician_name: str = "our technician",
    timezone_name: str = DEFAULT_TIMEZONE,
) -> bool:
    return SmsService().send_24h_reminder(
        job,
        customer,
        technician_name=technician_name,
        timezone_name=timezone_name,
    )


def send_1h_reminder(
    job: DispatchJob,
    customer: Customer,
    *,
    technician_name: str = "our technician",
    timezone_name: str = DEFAULT_TIMEZONE,
) -> bool:
    return SmsService().send_1h_reminder(
        job,
        customer,
        technician_name=technician_name,
        timezone_name=timezone_name,
    )
