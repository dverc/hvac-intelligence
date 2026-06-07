"""Onboarding provision API."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.organization import Organization
from app.models.technician import Technician


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


DEFAULT_BUSINESS_HOURS = {
    "monday": {"open": "08:00", "close": "17:00"},
    "tuesday": {"open": "08:00", "close": "17:00"},
    "wednesday": {"open": "08:00", "close": "17:00"},
    "thursday": {"open": "08:00", "close": "17:00"},
    "friday": {"open": "08:00", "close": "17:00"},
    "saturday": None,
    "sunday": None,
}


def _provision_payload(**overrides):
    phone = f"+1555{uuid.uuid4().int % 100000000:08d}"
    payload = {
        "business_name": f"Acme HVAC {_unique('co')}",
        "trade_type": "hvac",
        "phone_number": phone,
        "agent_name": "Alex",
        "timezone": "America/Los_Angeles",
        "business_hours": DEFAULT_BUSINESS_HOURS,
        "notification_email": "owner@example.com",
        "service_zip_codes": ["92612", "92614"],
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_provision_creates_org_with_correct_fields(api_client, db_session):
    payload = _provision_payload()
    response = await api_client.post("/api/v1/onboarding/provision", json=payload)
    assert response.status_code == 201
    body = response.json()

    org = await db_session.get(Organization, uuid.UUID(body["org_id"]))
    assert org is not None
    assert org.org_name == payload["business_name"]
    assert org.industry == "hvac"
    assert org.plan_tier == "starter"
    assert org.agent_name == "Alex"
    assert org.vapi_phone_number == payload["phone_number"]
    assert org.business_phone == payload["phone_number"]

    techs = (
        await db_session.execute(
            select(Technician).where(Technician.org_id == org.org_id)
        )
    ).scalars().all()
    assert len(techs) == 1
    assert techs[0].full_name == "On-Call Tech"

    assert body["org_name"] == payload["business_name"]
    assert body["agent_name"] == "Alex"
    assert body["dashboard_api_key"] == "test-api-key-for-tests"


@pytest.mark.asyncio
async def test_provision_slug_generated_from_business_name(api_client):
    payload = _provision_payload(business_name="Summit Air Conditioning")
    response = await api_client.post("/api/v1/onboarding/provision", json=payload)
    assert response.status_code == 201
    assert response.json()["slug"] == "summit-air-conditioning"


@pytest.mark.asyncio
async def test_provision_settings_contains_required_fields(api_client, db_session):
    payload = _provision_payload(trade_type="plumbing")
    response = await api_client.post("/api/v1/onboarding/provision", json=payload)
    assert response.status_code == 201

    org = await db_session.get(Organization, uuid.UUID(response.json()["org_id"]))
    assert org is not None
    settings = org.settings
    assert settings["timezone"] == payload["timezone"]
    assert settings["business_hours"]["monday"] == {"open": "08:00", "close": "17:00"}
    assert settings["trade_type"] == "plumbing"
    assert settings["service_area"]["zip_codes"] == ["92612", "92614"]


@pytest.mark.asyncio
async def test_provision_returns_400_when_business_name_missing(api_client):
    payload = _provision_payload()
    payload.pop("business_name")
    response = await api_client.post("/api/v1/onboarding/provision", json=payload)
    assert response.status_code == 400
    assert "business_name" in response.json()["detail"]


@pytest.mark.asyncio
async def test_provision_returns_400_when_phone_number_missing(api_client):
    payload = _provision_payload()
    payload.pop("phone_number")
    response = await api_client.post("/api/v1/onboarding/provision", json=payload)
    assert response.status_code == 400
    assert "phone_number" in response.json()["detail"]
