"""Outbound email via SendGrid HTTP API."""

from __future__ import annotations

import html
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


def send_email(to_address: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SendGrid. Returns False when unconfigured or on failure."""
    try:
        settings = get_settings()
        if not (settings.SENDGRID_API_KEY or "").strip():
            logger.warning("Email not configured — skipping")
            return False

        payload = {
            "personalizations": [{"to": [{"email": to_address}]}],
            "from": {
                "email": settings.REPORT_FROM_EMAIL,
                "name": settings.REPORT_FROM_NAME,
            },
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_body},
                {"type": "text/html", "value": html_body},
            ],
        }
        response = httpx.post(
            SENDGRID_API_URL,
            headers={
                "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30.0,
        )
        if response.status_code in (200, 202):
            return True
        logger.warning(
            "SendGrid returned status %s for %s: %s",
            response.status_code,
            to_address,
            response.text,
        )
        return False
    except Exception:
        logger.exception("Failed to send email to %s", to_address)
        return False


def build_weekly_report_html(org_name: str, stats: dict) -> tuple[str, str]:
    """Build HTML and plain-text bodies for the weekly client report."""
    safe_org = html.escape(org_name)
    total_calls = int(stats.get("total_calls", 0))
    calls_booked = int(stats.get("calls_booked", 0))
    calls_escalated = int(stats.get("calls_escalated", 0))
    new_customers = int(stats.get("new_customers", 0))
    churn_risk_high = int(stats.get("churn_risk_high", 0))
    busiest_day = html.escape(str(stats.get("busiest_day", "N/A")))
    top_issue_type = html.escape(str(stats.get("top_issue_type", "N/A")))

    summary = (
        f"Your AI receptionist handled {total_calls} call"
        f"{'s' if total_calls != 1 else ''} last week, booked {calls_booked} "
        f"service appointment{'s' if calls_booked != 1 else ''}, and escalated "
        f"{calls_escalated} call{'s' if calls_escalated != 1 else ''} to your team."
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Weekly AI Receptionist Report — {safe_org}</title>
</head>
<body style="font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; line-height: 1.5; max-width: 640px; margin: 0 auto; padding: 24px;">
  <header style="border-bottom: 2px solid #2563eb; padding-bottom: 16px; margin-bottom: 24px;">
    <h1 style="margin: 0 0 8px 0; font-size: 22px; color: #2563eb;">Weekly AI Receptionist Report</h1>
    <p style="margin: 0; font-size: 16px; color: #374151;">{safe_org}</p>
  </header>
  <p style="font-size: 15px; margin-bottom: 24px;">{html.escape(summary)}</p>
  <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
    <thead>
      <tr>
        <th style="text-align: left; padding: 10px 12px; background: #f3f4f6; border: 1px solid #e5e7eb;">Metric</th>
        <th style="text-align: right; padding: 10px 12px; background: #f3f4f6; border: 1px solid #e5e7eb;">Value</th>
      </tr>
    </thead>
    <tbody>
      <tr><td style="padding: 10px 12px; border: 1px solid #e5e7eb;">Total calls handled</td><td style="padding: 10px 12px; border: 1px solid #e5e7eb; text-align: right;">{total_calls}</td></tr>
      <tr><td style="padding: 10px 12px; border: 1px solid #e5e7eb;">Appointments booked</td><td style="padding: 10px 12px; border: 1px solid #e5e7eb; text-align: right;">{calls_booked}</td></tr>
      <tr><td style="padding: 10px 12px; border: 1px solid #e5e7eb;">Calls escalated to staff</td><td style="padding: 10px 12px; border: 1px solid #e5e7eb; text-align: right;">{calls_escalated}</td></tr>
      <tr><td style="padding: 10px 12px; border: 1px solid #e5e7eb;">New customers added</td><td style="padding: 10px 12px; border: 1px solid #e5e7eb; text-align: right;">{new_customers}</td></tr>
      <tr><td style="padding: 10px 12px; border: 1px solid #e5e7eb;">High / critical churn risk customers</td><td style="padding: 10px 12px; border: 1px solid #e5e7eb; text-align: right;">{churn_risk_high}</td></tr>
      <tr><td style="padding: 10px 12px; border: 1px solid #e5e7eb;">Busiest day</td><td style="padding: 10px 12px; border: 1px solid #e5e7eb; text-align: right;">{busiest_day}</td></tr>
      <tr><td style="padding: 10px 12px; border: 1px solid #e5e7eb;">Top issue type</td><td style="padding: 10px 12px; border: 1px solid #e5e7eb; text-align: right;">{top_issue_type}</td></tr>
    </tbody>
  </table>
  <p style="margin-top: 24px; font-size: 12px; color: #6b7280;">Sent automatically by HVAC Intelligence.</p>
</body>
</html>"""

    text_body = f"""Weekly AI Receptionist Report — {org_name}

{summary}

Total calls handled:     {total_calls}
Appointments booked:     {calls_booked}
Calls escalated:         {calls_escalated}
New customers added:     {new_customers}
High/critical churn:     {churn_risk_high}
Busiest day:             {stats.get('busiest_day', 'N/A')}
Top issue type:          {stats.get('top_issue_type', 'N/A')}

Sent automatically by HVAC Intelligence.
"""

    return html_body, text_body
