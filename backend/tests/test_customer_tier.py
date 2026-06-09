"""Customer tier model, API, and call-start prompt injection tests."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.constants import SEED_ORG_ID
from app.models.customer import Customer
from tests.conftest import sign_vapi_payload


@pytest.mark.asyncio
async def test_customer_created_with_default_tier_standard(db_session):
    customer = Customer(
        org_id=SEED_ORG_ID,
        full_name="Tier Default Test",
        phone_primary=f"+1555{uuid.uuid4().int % 100000000:08d}",
        customer_since=date.today(),
    )
    db_session.add(customer)
    await db_session.flush()
    await db_session.refresh(customer)

    assert customer.customer_tier == "standard"


@pytest.mark.asyncio
async def test_customer_tier_can_be_updated_to_vip_via_api(auth_client, seeded_customer):
    customer_id = seeded_customer["customer_id"]
    response = await auth_client.patch(
        f"/api/v1/customers/{customer_id}",
        json={"customer_tier": "vip"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["customer_tier"] == "vip"

    profile = await auth_client.get(f"/api/v1/customers/{customer_id}")
    assert profile.status_code == 200
    assert profile.json()["customer_tier"] == "vip"


async def _post_call_start(
    db_session,
    monkeypatch,
    *,
    phone: str,
    call_id: str,
) -> dict:
    from app.api import deps
    from app.main import app
    from app.pipeline import event_bus
    from app.rag.retriever import RAGRetriever
    from app.services.churn_service import ChurnService
    from app.services.customer_service import CustomerService
    from app.services.dispatch_service import DispatchService
    from app.services.ticket_service import TicketService
    from app.services.tool_executor import ToolExecutor

    monkeypatch.setattr(event_bus, "publish_call_active_event", AsyncMock())

    async def override_get_db():
        yield db_session

    customer_service = CustomerService(db_session)
    tool_executor = ToolExecutor(
        customer_service=customer_service,
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
                "id": call_id,
                "customer": {"number": phone},
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
    return response.json()


@pytest.mark.asyncio
async def test_vip_tier_injects_system_prompt(db_session, seeded_customer, monkeypatch):
    customer = await db_session.get(
        Customer, uuid.UUID(seeded_customer["customer_id"])
    )
    customer.customer_tier = "vip"
    await db_session.flush()

    data = await _post_call_start(
        db_session,
        monkeypatch,
        phone=seeded_customer["phone"],
        call_id="call-vip-tier",
    )
    prompt = data["assistantOverrides"]["model"]["systemPrompt"]
    assert "VIP CUSTOMER" in prompt
    assert "priority scheduling" in prompt.lower()


@pytest.mark.asyncio
async def test_preferred_tier_injects_system_prompt(
    db_session, seeded_customer, monkeypatch
):
    customer = await db_session.get(
        Customer, uuid.UUID(seeded_customer["customer_id"])
    )
    customer.customer_tier = "preferred"
    await db_session.flush()

    data = await _post_call_start(
        db_session,
        monkeypatch,
        phone=seeded_customer["phone"],
        call_id="call-preferred-tier",
    )
    prompt = data["assistantOverrides"]["model"]["systemPrompt"]
    assert "PREFERRED CUSTOMER" in prompt
    assert "annual maintenance plan" in prompt.lower()


@pytest.mark.asyncio
async def test_standard_tier_adds_nothing_to_system_prompt(
    db_session, seeded_customer, monkeypatch
):
    customer = await db_session.get(
        Customer, uuid.UUID(seeded_customer["customer_id"])
    )
    customer.customer_tier = "standard"
    await db_session.flush()

    data = await _post_call_start(
        db_session,
        monkeypatch,
        phone=seeded_customer["phone"],
        call_id="call-standard-tier",
    )
    prompt = data["assistantOverrides"]["model"]["systemPrompt"]
    assert "VIP CUSTOMER" not in prompt
    assert "PREFERRED CUSTOMER" not in prompt
