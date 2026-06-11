"""Tests for outbound campaign compliance and API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.constants import CONSENT_TYPE_OUTBOUND_CALL, SEED_ORG_ID
from app.models.customer import Customer
from app.models.outbound_campaign import ConsentRecord, OutboundCampaign
from app.services.compliance_service import (
    ComplianceService,
    check_calling_hours,
    get_disclosure_text,
)


@pytest.mark.asyncio
async def test_compliance_check_blocks_dnc_customer(db_session, seeded_customer):
    customer = seeded_customer["customer"]
    metadata = dict(customer.metadata_ or {})
    metadata["dnc"] = True
    customer.metadata_ = metadata
    await db_session.flush()

    service = ComplianceService(db_session)
    result = await service.check_outbound_eligibility(
        customer.customer_id, SEED_ORG_ID
    )
    assert result["eligible"] is False
    assert result["reason"] == "DNC_REGISTERED"


@pytest.mark.asyncio
async def test_compliance_check_blocks_no_consent(db_session, seeded_customer):
    service = ComplianceService(db_session)
    result = await service.check_outbound_eligibility(
        seeded_customer["customer"].customer_id, SEED_ORG_ID
    )
    assert result["eligible"] is False
    assert result["reason"] == "NO_CONSENT"


@pytest.mark.asyncio
async def test_compliance_check_allows_eligible_customer(db_session, seeded_customer):
    customer = seeded_customer["customer"]
    service = ComplianceService(db_session)
    await service.record_consent(
        customer.customer_id,
        SEED_ORG_ID,
        CONSENT_TYPE_OUTBOUND_CALL,
        "WRITTEN_FORM",
        "Customer signed outbound consent form",
    )
    result = await service.check_outbound_eligibility(
        customer.customer_id, SEED_ORG_ID
    )
    assert result["eligible"] is True
    assert result["reason"] == "ELIGIBLE"


def test_calling_hours_blocks_outside_window():
    # 949 area code → America/Los_Angeles; 7 AM local should be blocked
    early = datetime(2026, 6, 10, 14, 0, tzinfo=timezone.utc)  # 7 AM PDT
    assert check_calling_hours("9495551234", 8, 21, now=early) is False


def test_calling_hours_allows_inside_window():
    midday = datetime(2026, 6, 10, 20, 0, tzinfo=timezone.utc)  # 1 PM PDT
    assert check_calling_hours("9495551234", 8, 21, now=midday) is True


@pytest.mark.asyncio
async def test_consent_recording_saves_to_db(db_session, seeded_customer):
    customer = seeded_customer["customer"]
    service = ComplianceService(db_session)
    record = await service.record_consent(
        customer.customer_id,
        SEED_ORG_ID,
        CONSENT_TYPE_OUTBOUND_CALL,
        "VERBAL_INBOUND",
        "Customer agreed on inbound call",
        call_id="call-test-001",
    )
    assert record.consent_id is not None
    row = await db_session.get(ConsentRecord, record.consent_id)
    assert row is not None
    assert row.consent_text.startswith("Customer agreed")


@pytest.mark.asyncio
async def test_consent_revocation_sets_dnc(db_session, seeded_customer):
    customer = seeded_customer["customer"]
    service = ComplianceService(db_session)
    await service.record_consent(
        customer.customer_id,
        SEED_ORG_ID,
        CONSENT_TYPE_OUTBOUND_CALL,
        "VERBAL_INBOUND",
        "Initial consent",
    )
    await service.revoke_consent(
        customer.customer_id,
        SEED_ORG_ID,
        CONSENT_TYPE_OUTBOUND_CALL,
        "VERBAL",
    )
    refreshed = await db_session.get(Customer, customer.customer_id)
    assert refreshed is not None
    assert (refreshed.metadata_ or {}).get("dnc") is True


def test_disclosure_text_always_includes_ai_mention():
    friendly = get_disclosure_text("Desert Air HVAC", "FRIENDLY")
    formal = get_disclosure_text("SoCal Comfort Systems", "FORMAL")
    assert "AI" in friendly or "artificial intelligence" in friendly.lower()
    assert "artificial intelligence" in formal.lower()


def test_disclosure_text_always_includes_recording_mention():
    friendly = get_disclosure_text("Desert Air HVAC", "FRIENDLY")
    formal = get_disclosure_text("SoCal Comfort Systems", "FORMAL")
    assert "record" in friendly.lower()
    assert "record" in formal.lower()


def test_disclosure_text_never_contains_hvac_intelligence():
    text = get_disclosure_text("Desert Air HVAC", "FRIENDLY")
    assert "HVAC Intelligence" not in text


@pytest.mark.asyncio
async def test_campaign_creation_counts_eligible_customers(db_session, seeded_customer):
    from app.services.outbound_service import OutboundService

    customer = seeded_customer["customer"]
    compliance = ComplianceService(db_session)
    await compliance.record_consent(
        customer.customer_id,
        SEED_ORG_ID,
        CONSENT_TYPE_OUTBOUND_CALL,
        "WRITTEN_FORM",
        "Signed consent",
    )
    customer.metadata_ = {
        **(customer.metadata_ or {}),
        "churn_probability": 0.80,
    }
    await db_session.flush()

    service = OutboundService(db_session)
    campaign = await service.create_campaign(
        SEED_ORG_ID,
        {
            "campaign_name": "Test Reactivation",
            "campaign_type": "REACTIVATION",
            "churn_score_threshold": 0.60,
            "max_attempts": 2,
            "calling_hours_start": 9,
            "calling_hours_end": 18,
            "disclosure_style": "FRIENDLY",
        },
    )
    assert campaign.total_customers_targeted >= 1


@pytest.mark.asyncio
async def test_outbound_campaign_api_create(auth_client, db_session, seeded_customer):
    customer = seeded_customer["customer"]
    compliance = ComplianceService(db_session)
    await compliance.record_consent(
        customer.customer_id,
        SEED_ORG_ID,
        CONSENT_TYPE_OUTBOUND_CALL,
        "WRITTEN_FORM",
        "API test consent",
    )

    with patch(
        "app.tasks.celery_tasks.execute_outbound_campaign.delay",
    ):
        response = await auth_client.post(
            "/api/v1/outbound/campaigns",
            json={
                "campaign_name": "API Campaign",
                "campaign_type": "REACTIVATION",
                "churn_score_threshold": 0.60,
                "max_attempts": 2,
                "calling_hours_start": 9,
                "calling_hours_end": 18,
                "disclosure_style": "FRIENDLY",
            },
        )
    assert response.status_code == 201
    body = response.json()
    assert body["campaign_name"] == "API Campaign"
    assert body["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_outbound_campaign_api_list(auth_client, db_session):
    campaign = OutboundCampaign(
        org_id=SEED_ORG_ID,
        campaign_name="Listed Campaign",
        campaign_type="RETENTION",
        status="DRAFT",
        churn_score_threshold=0.75,
    )
    db_session.add(campaign)
    await db_session.flush()

    response = await auth_client.get("/api/v1/outbound/campaigns")
    assert response.status_code == 200
    names = [c["campaign_name"] for c in response.json()]
    assert "Listed Campaign" in names
