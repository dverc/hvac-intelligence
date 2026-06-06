"""Outbound SMS via Twilio."""

from __future__ import annotations

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def build_booking_confirmation_sms(
    customer_name: str,
    technician_name: str,
    scheduled_window: str,
    address: str,
    issue_type: str,
) -> str:
    """Build a concise booking confirmation SMS (target under 160 characters)."""
    first_name = customer_name.split()[0] if customer_name.strip() else "there"
    issue_label = issue_type.replace("_", " ").lower()
    message = (
        f"Hi {first_name}, your {issue_label} appointment is confirmed. "
        f"{technician_name} will arrive at {address} during {scheduled_window}. "
        "Reply STOP to opt out."
    )
    if len(message) > 160:
        short_address = address if len(address) <= 24 else f"{address[:21]}..."
        message = (
            f"Hi {first_name}, your {issue_label} appt is confirmed. "
            f"{technician_name} arrives {short_address} during {scheduled_window}. "
            "Reply STOP to opt out."
        )
    return message


def send_sms(to_number: str, message: str) -> bool:
    """Send an SMS via Twilio. Returns False when unconfigured or on failure."""
    try:
        settings = get_settings()
        if (
            not settings.TWILIO_ACCOUNT_SID
            or not settings.TWILIO_AUTH_TOKEN
            or not settings.TWILIO_FROM_NUMBER
        ):
            logger.warning("Twilio not configured — SMS not sent")
            return False

        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=settings.TWILIO_FROM_NUMBER,
            to=to_number,
        )
        return True
    except Exception:
        logger.exception("Failed to send SMS to %s", to_number)
        return False
