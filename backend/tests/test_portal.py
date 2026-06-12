"""Customer portal API tests (public, no JWT)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import SEED_ORG_ID
from app.models.dispatch_job import DispatchJob
from app.models.org_settings import OrgSettings


async def _seed_portal_jobs(db_session: AsyncSession, seeded_customer: dict) -> DispatchJob:
    future_start = datetime.now(timezone.utc) + timedelta(days=3)
    future_end = future_start + timedelta(hours=2)
    upcoming = DispatchJob(
        org_id=SEED_ORG_ID,
        job_number=f"DX-PORTAL-{uuid.uuid4().hex[:6].upper()}",
        customer_id=seeded_customer["customer"].customer_id,
        technician_id=uuid.UUID(seeded_customer["technician_id"]),
        issue_type="AC_FAILURE",
        job_status="SCHEDULED",
        scheduled_window_start=future_start,
        scheduled_window_end=future_end,
        created_by="TEST",
    )
    past_start = datetime.now(timezone.utc) - timedelta(days=5)
    past_end = past_start + timedelta(hours=2)
    past = DispatchJob(
        org_id=SEED_ORG_ID,
        job_number=f"DX-PORTAL-P-{uuid.uuid4().hex[:6].upper()}",
        customer_id=seeded_customer["customer"].customer_id,
        technician_id=uuid.UUID(seeded_customer["technician_id"]),
        issue_type="MAINTENANCE",
        job_status="COMPLETED",
        scheduled_window_start=past_start,
        scheduled_window_end=past_end,
        created_by="TEST",
    )
    db_session.add(upcoming)
    db_session.add(past)
    await db_session.flush()
    return upcoming


@pytest.mark.asyncio
async def test_portal_identify_found(
    api_client: AsyncClient, db_session: AsyncSession, seeded_customer
):
    upcoming = await _seed_portal_jobs(db_session, seeded_customer)
    phone = seeded_customer["phone"]

    response = await api_client.post(
        "/api/v1/portal/identify",
        json={"phone": phone},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["customer_id"] == seeded_customer["customer_id"]
    assert body["name"] == "Sarah Mitchell"
    assert len(body["upcoming_appointments"]) >= 1
    assert any(a["id"] == str(upcoming.job_id) for a in body["upcoming_appointments"])
    assert len(body["past_appointments"]) >= 1


@pytest.mark.asyncio
async def test_portal_identify_not_found(api_client: AsyncClient):
    response = await api_client.post(
        "/api/v1/portal/identify",
        json={"phone": "+15559998888"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is False
    assert body.get("customer_id") is None


@pytest.mark.asyncio
async def test_portal_identify_rate_limit_structure(api_client: AsyncClient):
    response = await api_client.post(
        "/api/v1/portal/identify",
        json={"phone": "9495551234"},
    )
    assert response.status_code == 200
    assert "found" in response.json()


@pytest.mark.asyncio
async def test_portal_request_service(api_client: AsyncClient, db_session: AsyncSession):
    phone = f"+1555{uuid.uuid4().int % 100000000:08d}"
    response = await api_client.post(
        "/api/v1/portal/request",
        json={
            "phone": phone,
            "name": "Portal Guest",
            "issue_type": "AC Not Cooling",
            "description": "Unit not cooling upstairs",
            "preferred_date": "2026-06-15",
            "preferred_time_window": "Morning (8AM-12PM)",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["ticket_number"].startswith("TKT-")
    assert "contact you" in body["message"].lower()


@pytest.mark.asyncio
async def test_portal_appointments_endpoint(
    api_client: AsyncClient, db_session: AsyncSession, seeded_customer
):
    upcoming = await _seed_portal_jobs(db_session, seeded_customer)
    customer_id = seeded_customer["customer_id"]

    response = await api_client.get(f"/api/v1/portal/appointments/{customer_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == customer_id
    assert body["name"] == "Sarah Mitchell"
    assert body["timezone"] == "America/Los_Angeles"
    assert any(a["job_number"] == upcoming.job_number for a in body["upcoming_appointments"])


@pytest.mark.asyncio
async def test_portal_appointments_returns_org_timezone_from_settings(
    api_client: AsyncClient, db_session: AsyncSession, seeded_customer
):
    await _seed_portal_jobs(db_session, seeded_customer)
    customer_id = seeded_customer["customer_id"]

    settings = (
        await db_session.execute(
            select(OrgSettings).where(OrgSettings.org_id == SEED_ORG_ID)
        )
    ).scalar_one_or_none()
    if settings is None:
        settings = OrgSettings(org_id=SEED_ORG_ID, agent_name="AI Assistant")
        db_session.add(settings)
    settings.timezone = "America/Chicago"
    await db_session.flush()

    response = await api_client.get(f"/api/v1/portal/appointments/{customer_id}")
    assert response.status_code == 200
    assert response.json()["timezone"] == "America/Chicago"


@pytest.mark.asyncio
async def test_portal_reschedule_request(
    api_client: AsyncClient, db_session: AsyncSession, seeded_customer
):
    upcoming = await _seed_portal_jobs(db_session, seeded_customer)
    response = await api_client.post(
        "/api/v1/portal/reschedule-request",
        json={
            "customer_id": seeded_customer["customer_id"],
            "appointment_id": str(upcoming.job_id),
            "preferred_date": "2026-06-20",
            "preferred_time_window": "Afternoon (12PM-5PM)",
            "reason": "Work conflict",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "reschedule request submitted" in body["message"].lower()
