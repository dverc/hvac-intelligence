"""THE security test: cross-tenant data must never leak.

These tests assert that records belonging to org B are invisible/unwritable when
operating under org A — at the service layer AND through the dashboard API.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.tenant import get_dashboard_org_id
from app.models.call_transcript import CallTranscript
from app.schemas.customer import CustomerUpdate
from app.services.customer_service import CustomerService
from app.services.tenant_service import TenantService
from tests.conftest import sign_vapi_payload


@pytest.mark.asyncio
async def test_get_customer_cross_tenant_returns_none(
    db_session, make_org, make_customer
):
    org_a = await make_org(name="Org A")
    org_b = await make_org(name="Org B")
    cust_b = await make_customer(org_id=org_b.org_id, full_name="B Customer")

    service = CustomerService(db_session)

    # Under org A, B's customer must be invisible.
    assert await service.get_by_id(cust_b.customer_id, org_a.org_id) is None
    # Under its own org it is visible.
    assert await service.get_by_id(cust_b.customer_id, org_b.org_id) is not None


@pytest.mark.asyncio
async def test_update_cross_tenant_customer_fails(
    db_session, make_org, make_customer
):
    org_a = await make_org(name="Org A")
    org_b = await make_org(name="Org B")
    cust_b = await make_customer(org_id=org_b.org_id, full_name="B Customer")

    service = CustomerService(db_session)
    result = await service.update_customer(
        cust_b.customer_id,
        CustomerUpdate(full_name="Hacked"),
        org_a.org_id,
    )
    assert result is None

    # Confirm B's row is unchanged.
    refreshed = await service.get_by_id(cust_b.customer_id, org_b.org_id)
    assert refreshed.full_name == "B Customer"


@pytest.mark.asyncio
async def test_transcripts_scoped_to_org_excludes_other_tenant(
    db_session, make_org, make_customer
):
    org_a = await make_org(name="Org A")
    org_b = await make_org(name="Org B")
    cust_b = await make_customer(org_id=org_b.org_id)

    from datetime import datetime, timezone

    transcript = CallTranscript(
        call_id=f"iso-{uuid.uuid4().hex[:8]}",
        org_id=org_b.org_id,
        customer_id=cust_b.customer_id,
        call_direction="INBOUND",
        call_start_utc=datetime.now(timezone.utc),
        call_outcome="DISPATCHED",
    )
    db_session.add(transcript)
    await db_session.flush()

    from sqlalchemy import select

    # Scoped to org A: B's transcript is invisible.
    rows_a = (
        await db_session.execute(
            select(CallTranscript).where(
                CallTranscript.org_id == org_a.org_id,
                CallTranscript.customer_id == cust_b.customer_id,
            )
        )
    ).scalars().all()
    assert rows_a == []

    # Scoped to org B: visible.
    rows_b = (
        await db_session.execute(
            select(CallTranscript).where(
                CallTranscript.org_id == org_b.org_id,
                CallTranscript.customer_id == cust_b.customer_id,
            )
        )
    ).scalars().all()
    assert len(rows_b) == 1


@pytest.mark.asyncio
async def test_dashboard_cannot_fetch_other_tenant_customer(
    auth_client, db_session, make_org, make_customer
):
    from app.main import app

    org_a = await make_org(name="Org A")
    org_b = await make_org(name="Org B")
    cust_b = await make_customer(org_id=org_b.org_id, full_name="B Customer")

    # Dashboard scoped to org A (override the stopgap dependency).
    app.dependency_overrides[get_dashboard_org_id] = lambda: org_a.org_id
    try:
        resp_a = await auth_client.get(f"/api/v1/customers/{cust_b.customer_id}")
        assert resp_a.status_code == 404
    finally:
        app.dependency_overrides.pop(get_dashboard_org_id, None)

    # Dashboard scoped to org B can fetch it.
    app.dependency_overrides[get_dashboard_org_id] = lambda: org_b.org_id
    try:
        resp_b = await auth_client.get(f"/api/v1/customers/{cust_b.customer_id}")
        assert resp_b.status_code == 200
        assert resp_b.json()["full_name"] == "B Customer"
    finally:
        app.dependency_overrides.pop(get_dashboard_org_id, None)


@pytest.mark.asyncio
async def test_call_start_resolves_tenant_by_called_number(
    db_session, make_org, make_customer, monkeypatch
):
    from unittest.mock import AsyncMock

    from httpx import ASGITransport, AsyncClient

    from app.api import deps
    from app.main import app
    from app.pipeline import event_bus
    from app.rag.retriever import RAGRetriever
    from app.services.churn_service import ChurnService
    from app.services.customer_service import CustomerService
    from app.services.dispatch_service import DispatchService
    from app.services.ticket_service import TicketService
    from app.services.tool_executor import ToolExecutor

    # Org B owns a distinct inbound business number.
    business_phone = f"+1555{uuid.uuid4().int % 100000000:08d}"
    org_b = await make_org(name="Beta HVAC", business_phone=business_phone)
    await make_customer(org_id=org_b.org_id, full_name="Beta Caller")
    await db_session.flush()
    TenantService(db_session).invalidate_cache()

    monkeypatch.setattr(event_bus, "publish_call_active_event", AsyncMock())

    async def override_get_db():
        yield db_session

    tool_executor = ToolExecutor(
        customer_service=CustomerService(db_session),
        dispatch_service=DispatchService(db_session),
        churn_service=ChurnService(db_session),
        ticket_service=TicketService(db_session),
        rag_retriever=AsyncMock(spec=RAGRetriever),
    )
    app.dependency_overrides[deps.get_db] = override_get_db

    async def override_build_tool_executor(_db):
        return tool_executor

    monkeypatch.setattr(deps, "build_tool_executor", override_build_tool_executor)

    payload = {
        "message": {
            "type": "call-start",
            "call": {
                "id": f"call-{uuid.uuid4().hex[:8]}",
                "phoneNumber": {"number": business_phone},
                "customer": {"number": "+15551112222"},
            },
        }
    }
    body, signature = sign_vapi_payload(payload)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhook/vapi",
            content=body,
            headers={"x-vapi-signature": signature, "content-type": "application/json"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    overrides = response.json()["assistantOverrides"]
    # Resolved tenant is Beta HVAC (org B), NOT the seed/default org.
    assert overrides["variableValues"]["company_name"] == "Beta HVAC"
