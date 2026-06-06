from unittest.mock import MagicMock, patch

import httpx

from app.services.email_service import build_weekly_report_html, send_email

SAMPLE_STATS = {
    "total_calls": 42,
    "calls_booked": 18,
    "calls_escalated": 3,
    "new_customers": 5,
    "churn_risk_high": 2,
    "busiest_day": "Tuesday",
    "top_issue_type": "Ac Failure",
}


def test_send_email_returns_false_when_sendgrid_api_key_empty():
    with patch("app.services.email_service.get_settings") as mock_settings:
        mock_settings.return_value.SENDGRID_API_KEY = ""
        with patch("app.services.email_service.httpx.post") as mock_post:
            assert send_email("user@example.com", "Subject", "<p>Hi</p>", "Hi") is False
    mock_post.assert_not_called()


def test_send_email_returns_true_when_httpx_call_succeeds():
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.text = ""

    with patch("app.services.email_service.get_settings") as mock_settings:
        mock_settings.return_value.SENDGRID_API_KEY = "sg-test-key"
        mock_settings.return_value.REPORT_FROM_EMAIL = "reports@hvac-intelligence.com"
        mock_settings.return_value.REPORT_FROM_NAME = "HVAC Intelligence"
        with patch("app.services.email_service.httpx.post", return_value=mock_response) as mock_post:
            assert send_email("user@example.com", "Weekly Report", "<p>Hi</p>", "Hi") is True

    mock_post.assert_called_once()
    assert mock_post.call_args.kwargs["json"]["personalizations"][0]["to"][0]["email"] == (
        "user@example.com"
    )


def test_send_email_returns_false_when_httpx_call_fails():
    with patch("app.services.email_service.get_settings") as mock_settings:
        mock_settings.return_value.SENDGRID_API_KEY = "sg-test-key"
        mock_settings.return_value.REPORT_FROM_EMAIL = "reports@hvac-intelligence.com"
        mock_settings.return_value.REPORT_FROM_NAME = "HVAC Intelligence"
        with patch(
            "app.services.email_service.httpx.post",
            side_effect=httpx.HTTPError("network error"),
        ):
            assert send_email("user@example.com", "Subject", "<p>Hi</p>", "Hi") is False


def test_build_weekly_report_html_returns_tuple_of_non_empty_strings():
    html_body, text_body = build_weekly_report_html("Acme HVAC", SAMPLE_STATS)
    assert isinstance(html_body, str)
    assert isinstance(text_body, str)
    assert html_body.strip()
    assert text_body.strip()


def test_build_weekly_report_html_includes_org_name():
    html_body, text_body = build_weekly_report_html("Acme HVAC Services", SAMPLE_STATS)
    assert "Acme HVAC Services" in html_body
    assert "Acme HVAC Services" in text_body
