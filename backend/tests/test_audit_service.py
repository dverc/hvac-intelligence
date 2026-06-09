from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.constants import SEED_ORG_ID
from app.models.audit_log import AuditLog
from app.services.audit_service import (
    ACTOR_VAPI,
    AUDIT_CREATE,
    AUDIT_UPDATE,
    log_action,
)


@pytest.mark.asyncio
async def test_log_action_creates_audit_log_row(db_session):
    await log_action(
        db_session,
        str(SEED_ORG_ID),
        ACTOR_VAPI,
        AUDIT_CREATE,
        "customer",
        "customer-123",
        new_value={"name": "Jane Doe", "phone": "+15551234567"},
        call_id="call-abc",
    )

    row = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.resource_id == "customer-123")
        )
    ).scalar_one()

    assert row.org_id == str(SEED_ORG_ID)
    assert row.actor == ACTOR_VAPI
    assert row.action == AUDIT_CREATE
    assert row.resource_type == "customer"
    assert row.resource_id == "customer-123"
    assert row.new_value == {"name": "Jane Doe", "phone": "+15551234567"}
    assert row.call_id == "call-abc"


@pytest.mark.asyncio
async def test_log_action_does_not_raise_when_db_commit_fails(db_session):
    with patch.object(db_session, "commit", new_callable=AsyncMock) as mock_commit:
        mock_commit.side_effect = RuntimeError("db unavailable")
        await log_action(
            db_session,
            str(SEED_ORG_ID),
            ACTOR_VAPI,
            AUDIT_UPDATE,
            "dispatch_job",
            "job-456",
            new_value={"priority": "P1"},
        )


@pytest.mark.asyncio
async def test_log_action_records_org_action_resource_fields(db_session):
    await log_action(
        db_session,
        str(SEED_ORG_ID),
        ACTOR_VAPI,
        AUDIT_UPDATE,
        "equipment",
        "equip-789",
        new_value={"make": "Carrier", "model": "Infinity"},
    )

    row = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.resource_id == "equip-789")
        )
    ).scalar_one()

    assert row.org_id == str(SEED_ORG_ID)
    assert row.action == AUDIT_UPDATE
    assert row.resource_type == "equipment"
    assert row.resource_id == "equip-789"


@pytest.mark.asyncio
async def test_audit_logs_endpoint_returns_200_with_correct_structure(
    auth_client,
    db_session,
):
    await log_action(
        db_session,
        str(SEED_ORG_ID),
        ACTOR_VAPI,
        AUDIT_CREATE,
        "customer",
        "audit-endpoint-customer",
        new_value={"name": "Test User"},
    )

    response = await auth_client.get(
        "/api/v1/audit/logs",
        params={"org_id": str(SEED_ORG_ID), "limit": 10, "offset": 0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["org_id"] == str(SEED_ORG_ID)
    assert isinstance(body["total"], int)
    assert body["total"] >= 1
    assert isinstance(body["items"], list)
    item = next(
        entry for entry in body["items"] if entry["resource_id"] == "audit-endpoint-customer"
    )
    assert set(item) == {
        "id",
        "org_id",
        "actor",
        "action",
        "resource_type",
        "resource_id",
        "old_value",
        "new_value",
        "ip_address",
        "call_id",
        "created_at",
    }
    assert item["action"] == AUDIT_CREATE
    assert item["resource_type"] == "customer"


@pytest.mark.asyncio
async def test_audit_logs_endpoint_filters_by_resource_type(auth_client, db_session):
    await log_action(
        db_session,
        str(SEED_ORG_ID),
        ACTOR_VAPI,
        AUDIT_CREATE,
        "customer",
        "filter-customer",
        new_value={"name": "Filter Customer"},
    )
    await log_action(
        db_session,
        str(SEED_ORG_ID),
        ACTOR_VAPI,
        AUDIT_CREATE,
        "support_ticket",
        "filter-ticket",
        new_value={"subject": "Leak"},
    )

    response = await auth_client.get(
        "/api/v1/audit/logs",
        params={
            "org_id": str(SEED_ORG_ID),
            "resource_type": "support_ticket",
            "limit": 50,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert all(item["resource_type"] == "support_ticket" for item in body["items"])
    assert any(item["resource_id"] == "filter-ticket" for item in body["items"])
    assert all(item["resource_id"] != "filter-customer" for item in body["items"])
