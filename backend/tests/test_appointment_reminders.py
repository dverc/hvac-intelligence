"""Tests for appointment reminder Celery tasks."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.core.constants import SEED_ORG_ID
from app.ml.sync_db import get_sync_session
from app.models.customer import Customer
from app.models.dispatch_job import DispatchJob
from app.models.technician import Technician
from app.pipeline.tasks import (
    send_appointment_reminder_1h,
    send_appointment_reminder_24h,
)


def _create_reminder_job(
    session,
    *,
    window_start: datetime,
) -> tuple[DispatchJob, Customer, Technician]:
    tech = Technician(
        org_id=SEED_ORG_ID,
        employee_number=f"T-RM-{uuid.uuid4().hex[:8]}",
        full_name="Reminder Tech",
        phone="+15550009999",
        hire_date=date(2020, 1, 1),
        tenure_years=Decimal("5"),
    )
    customer = Customer(
        org_id=SEED_ORG_ID,
        full_name="Sarah Mitchell",
        phone_primary=f"+1555{uuid.uuid4().int % 100000000:08d}",
        address_line1="123 Main St",
        city="Irvine",
        state="CA",
        zip="92612",
        customer_since=date(2019, 6, 1),
        contract_type="ANNUAL_MAINTENANCE",
    )
    session.add(tech)
    session.add(customer)
    session.flush()

    job = DispatchJob(
        job_number=f"DX-RM-{uuid.uuid4().hex[:8]}",
        org_id=SEED_ORG_ID,
        customer_id=customer.customer_id,
        technician_id=tech.technician_id,
        issue_type="AC_NO_COOLING",
        priority="P2",
        job_status="SCHEDULED",
        issue_description="Reminder test job",
        scheduled_window_start=window_start,
        scheduled_window_end=window_start + timedelta(hours=2),
    )
    session.add(job)
    session.commit()
    return job, customer, tech


def _cleanup_reminder_fixtures(session, job, customer, tech) -> None:
    session.delete(job)
    session.delete(customer)
    session.delete(tech)
    session.commit()


def test_send_appointment_reminder_24h_sends_sms(database_ready):
    session = get_sync_session()
    now = datetime.now(timezone.utc)
    job, customer, tech = _create_reminder_job(
        session,
        window_start=now + timedelta(hours=23),
    )

    try:
        with patch("app.pipeline.tasks.send_sms", return_value=True) as mock_send:
            result = send_appointment_reminder_24h.run(str(job.job_id))

        assert result["status"] == "ok"
        mock_send.assert_called_once()
        message = mock_send.call_args[0][1]
        assert "reminder" in message.lower()
        assert "tomorrow" in message.lower()
        assert "Reply STOP" in message

        session.refresh(job)
        assert job.reminder_24h_sent_at is not None
    finally:
        _cleanup_reminder_fixtures(session, job, customer, tech)
        session.close()


def test_send_appointment_reminder_24h_skips_outside_window(database_ready):
    session = get_sync_session()
    now = datetime.now(timezone.utc)
    job, customer, tech = _create_reminder_job(
        session,
        window_start=now + timedelta(hours=48),
    )

    try:
        with patch("app.pipeline.tasks.send_sms", return_value=True) as mock_send:
            result = send_appointment_reminder_24h.run(str(job.job_id))

        assert result["status"] == "skipped"
        assert result["reason"] == "outside_window"
        mock_send.assert_not_called()
    finally:
        _cleanup_reminder_fixtures(session, job, customer, tech)
        session.close()


def test_send_appointment_reminder_1h_sends_sms(database_ready):
    session = get_sync_session()
    now = datetime.now(timezone.utc)
    job, customer, tech = _create_reminder_job(
        session,
        window_start=now + timedelta(minutes=60),
    )

    try:
        with patch("app.pipeline.tasks.send_sms", return_value=True) as mock_send:
            result = send_appointment_reminder_1h.run(str(job.job_id))

        assert result["status"] == "ok"
        mock_send.assert_called_once()
        message = mock_send.call_args[0][1]
        assert "on the way" in message.lower()
        assert "Reply STOP" in message

        session.refresh(job)
        assert job.reminder_1h_sent_at is not None
    finally:
        _cleanup_reminder_fixtures(session, job, customer, tech)
        session.close()


def test_reminder_not_sent_when_twilio_unconfigured(database_ready):
    session = get_sync_session()
    now = datetime.now(timezone.utc)
    job, customer, tech = _create_reminder_job(
        session,
        window_start=now + timedelta(hours=23),
    )

    try:
        with patch("app.pipeline.tasks.send_sms", return_value=False) as mock_send:
            result = send_appointment_reminder_24h.run(str(job.job_id))

        assert result["status"] == "skipped"
        mock_send.assert_called_once()

        session.refresh(job)
        assert job.reminder_24h_sent_at is None
    finally:
        _cleanup_reminder_fixtures(session, job, customer, tech)
        session.close()
