from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.services.sms_service import (
    SmsService,
    normalize_phone_to_e164,
    send_sms,
)


def test_send_sms_calls_twilio_when_configured():
    mock_messages = MagicMock()
    mock_result = MagicMock()
    mock_result.sid = "SM123456"
    mock_messages.create.return_value = mock_result
    mock_client = MagicMock()
    mock_client.messages = mock_messages

    with patch("app.services.sms_service.get_settings") as mock_settings:
        mock_settings.return_value.TWILIO_ACCOUNT_SID = "test_sid"
        mock_settings.return_value.TWILIO_AUTH_TOKEN = "test_token"
        mock_settings.return_value.TWILIO_FROM_NUMBER = "+15550001111"
        with patch("twilio.rest.Client", return_value=mock_client):
            assert send_sms("9493313190", "Your appointment is confirmed.") is True

    mock_messages.create.assert_called_once_with(
        body="Your appointment is confirmed.",
        from_="+15550001111",
        to="+19493313190",
    )


def test_send_sms_skips_when_not_configured():
    mock_client = MagicMock()
    with patch("app.services.sms_service.get_settings") as mock_settings:
        mock_settings.return_value.TWILIO_ACCOUNT_SID = ""
        mock_settings.return_value.TWILIO_AUTH_TOKEN = ""
        mock_settings.return_value.TWILIO_FROM_NUMBER = ""
        with patch("twilio.rest.Client", mock_client):
            assert send_sms("+15551234567", "Test message") is False
    mock_client.assert_not_called()


def test_phone_normalization():
    assert normalize_phone_to_e164("9493313190") == "+19493313190"
    assert normalize_phone_to_e164("(949) 331-3190") == "+19493313190"
    assert normalize_phone_to_e164("+19493313190") == "+19493313190"
    assert normalize_phone_to_e164("1-949-331-3190") == "+19493313190"
    assert normalize_phone_to_e164("949 331 3190") == "+19493313190"
    assert normalize_phone_to_e164("") == ""
    assert normalize_phone_to_e164("   ") == ""


def test_booking_confirmation_message_format():
    window_start = datetime(2026, 6, 10, 17, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 6, 10, 19, 0, tzinfo=timezone.utc)
    customer = Customer(
        org_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        full_name="Sarah Mitchell",
        phone_primary="+19493313190",
        customer_since=datetime(2020, 1, 1).date(),
        contract_type="RESIDENTIAL_OTC",
    )
    job = DispatchJob(
        job_number="DX-SMS-001",
        org_id=customer.org_id,
        customer_id=uuid.uuid4(),
        issue_type="AC_NO_COOLING",
        priority="P2",
        scheduled_window_start=window_start,
        scheduled_window_end=window_end,
    )

    with patch("app.services.sms_service.send_sms", return_value=True) as mock_send:
        sent = SmsService().send_booking_confirmation(
            job,
            customer,
            technician_name="Mike Johnson",
            timezone_name="America/Los_Angeles",
        )

    assert sent is True
    message = mock_send.call_args[0][1]
    assert "Sarah" in message
    assert "Mike Johnson" in message
    assert "AC not cooling" in message
    assert "Reply STOP to opt out." in message
    assert "between" in message
