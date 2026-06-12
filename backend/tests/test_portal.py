"""Customer portal API tests (public, no JWT)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import SEED_ORG_ID
from app.core.tenant import get_fallback_dashboard_org_id
from app.models.dispatch_job import DispatchJob
from app.models.org_settings import OrgSettings
from app.services.portal_service import resolve_portal_org_id


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
async def test_resolve_portal_org_id_by_slug(db_session: AsyncSession):
    org_id = await resolve_portal_org_id("hvac-demo", db_session)
    assert org_id == SEED_ORG_ID


@pytest.mark.asyncio
async def test_resolve_portal_org_id_case_insensitive(db_session: AsyncSession):
    org_id = await resolve_portal_org_id("HVAC-DEMO", db_session)
    assert org_id == SEED_ORG_ID

    org_id_by_name = await resolve_portal_org_id("hvac intelligence demo", db_session)
    assert org_id_by_name == SEED_ORG_ID


@pytest.mark.asyncio
async def test_resolve_portal_org_id_falls_back_when_missing_or_unknown(
    db_session: AsyncSession,
):
    fallback = get_fallback_dashboard_org_id()
    assert await resolve_portal_org_id(None, db_session) == fallback
    assert await resolve_portal_org_id("", db_session) == fallback
    assert await resolve_portal_org_id("unknown-org-slug", db_session) == fallback


@pytest.mark.asyncio
async def test_portal_identify_with_org_query_param(
    api_client: AsyncClient, db_session: AsyncSession, seeded_customer
):
    await _seed_portal_jobs(db_session, seeded_customer)
    phone = seeded_customer["phone"]

    response = await api_client.post(
        "/api/v1/portal/identify?org=hvac-demo",
        json={"phone": phone},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["customer_id"] == seeded_customer["customer_id"]


@pytest.mark.asyncio
async def test_portal_identify_missing_org_returns_400_in_production(
    api_client: AsyncClient, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "ENVIRONMENT", "production")

    response = await api_client.post(
        "/api/v1/portal/identify",
        json={"phone": "+15559998888"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "org parameter required"


@pytest.mark.asyncio
async def test_resolve_portal_org_id_duplicate_org_names_returns_oldest(
    db_session: AsyncSession, make_org, caplog
):
    first = await make_org(name="Duplicate Name Co", slug="dup-name-first")
    second = await make_org(name="Duplicate Name Co", slug="dup-name-second")
    await db_session.flush()
    assert first.org_id != second.org_id

    with caplog.at_level(logging.WARNING):
        org_id = await resolve_portal_org_id("duplicate name co", db_session)

    assert org_id == first.org_id
    assert any(
        "Multiple organizations matched portal org" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_portal_appointments_rejects_cross_tenant_customer(
    api_client: AsyncClient,
    db_session: AsyncSession,
    seeded_customer,
    make_org,
):
    org_b = await make_org(name="Portal Isolation Org B", slug="portal-isolation-b")
    await db_session.flush()
    customer_id = seeded_customer["customer_id"]

    response = await api_client.get(
        f"/api/v1/portal/appointments/{customer_id}",
        params={"org": org_b.slug},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found"


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
