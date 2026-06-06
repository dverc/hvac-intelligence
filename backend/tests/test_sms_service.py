from unittest.mock import MagicMock, patch

from app.services.sms_service import build_booking_confirmation_sms, send_sms


def test_send_sms_returns_false_when_credentials_empty():
    mock_client = MagicMock()
    with patch("app.services.sms_service.get_settings") as mock_settings:
        mock_settings.return_value.TWILIO_ACCOUNT_SID = ""
        mock_settings.return_value.TWILIO_AUTH_TOKEN = ""
        mock_settings.return_value.TWILIO_FROM_NUMBER = ""
        with patch("twilio.rest.Client", mock_client):
            assert send_sms("+15551234567", "Test message") is False
    mock_client.assert_not_called()


def test_build_booking_confirmation_sms_contains_customer_name_and_stays_short():
    message = build_booking_confirmation_sms(
        customer_name="Sarah Mitchell",
        technician_name="Test Tech",
        scheduled_window="Monday morning",
        address="123 Main St, Irvine, CA 92612",
        issue_type="AC_FAILURE",
    )
    assert isinstance(message, str)
    assert "Sarah" in message
    assert len(message) < 320


def test_send_sms_returns_true_when_twilio_client_mocked():
    mock_messages = MagicMock()
    mock_client = MagicMock()
    mock_client.messages = mock_messages

    with patch("app.services.sms_service.get_settings") as mock_settings:
        mock_settings.return_value.TWILIO_ACCOUNT_SID = "test_sid"
        mock_settings.return_value.TWILIO_AUTH_TOKEN = "test_token"
        mock_settings.return_value.TWILIO_FROM_NUMBER = "+15550001111"
        with patch("twilio.rest.Client", return_value=mock_client):
            assert send_sms("+15551234567", "Your appointment is confirmed.") is True

    mock_messages.create.assert_called_once_with(
        body="Your appointment is confirmed.",
        from_="+15550001111",
        to="+15551234567",
    )
