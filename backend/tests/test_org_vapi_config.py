from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import get_settings
from app.core.constants import SEED_ORG_ID
from app.services.tenant_service import TenantService
from tests.conftest import sign_vapi_payload


async def _post_call_start(api_client, *, call_id: str, caller_phone: str = "+15551234567"):
    payload = {
        "message": {
            "type": "call-start",
            "call": {
                "id": call_id,
                "customer": {"number": caller_phone},
            },
        }
    }
    body, signature = sign_vapi_payload(payload)
    return await api_client.post(
        "/webhook/vapi",
        content=body,
        headers={"x-vapi-signature": signature, "content-type": "application/json"},
    )


@pytest.mark.asyncio
async def test_call_start_uses_org_vapi_assistant_id(api_client, db_session):
    from app.models.organization import Organization

    org = await db_session.get(Organization, SEED_ORG_ID)
    org.vapi_assistant_id = "org-specific-assistant-id"
    await db_session.flush()

    with patch(
        "app.api.deps.build_tool_executor",
        new=AsyncMock(
            side_effect=lambda db: _mock_tool_executor(db_session),
        ),
    ):
        response = await _post_call_start(api_client, call_id="call-org-assistant")

    assert response.status_code == 200
    assert response.json()["assistantOverrides"]["assistantId"] == "org-specific-assistant-id"


@pytest.mark.asyncio
async def test_call_start_falls_back_to_global_vapi_assistant_id(api_client, db_session):
    from app.models.organization import Organization

    org = await db_session.get(Organization, SEED_ORG_ID)
    org.vapi_assistant_id = None
    await db_session.flush()

    with patch(
        "app.api.deps.build_tool_executor",
        new=AsyncMock(
            side_effect=lambda db: _mock_tool_executor(db_session),
        ),
    ):
        response = await _post_call_start(api_client, call_id="call-global-assistant")

    assert response.status_code == 200
    assert (
        response.json()["assistantOverrides"]["assistantId"]
        == get_settings().VAPI_ASSISTANT_ID
    )


@pytest.mark.asyncio
async def test_call_start_injects_agent_name_into_system_prompt(api_client, db_session):
    from app.models.organization import Organization

    org = await db_session.get(Organization, SEED_ORG_ID)
    org.agent_name = "Alex"
    await db_session.flush()

    with patch(
        "app.api.deps.build_tool_executor",
        new=AsyncMock(
            side_effect=lambda db: _mock_tool_executor(db_session),
        ),
    ):
        response = await _post_call_start(api_client, call_id="call-agent-name")

    assert response.status_code == 200
    prompt = response.json()["assistantOverrides"]["model"]["systemPrompt"]
    assert "Your name is Alex." in prompt


@pytest.mark.asyncio
async def test_tenant_resolution_finds_org_by_vapi_phone_number(db_session, make_org):
    org = await make_org(name="Dedicated Line Org")
    org.vapi_phone_number = "+15558881234"
    await db_session.flush()
    service = TenantService(db_session)
    service.invalidate_cache()

    resolved = await service.get_tenant_by_phone("+15558881234")

    assert resolved.org_id == org.org_id


def _mock_tool_executor(db_session):
    from unittest.mock import AsyncMock

    from app.rag.retriever import RAGRetriever
    from app.services.churn_service import ChurnService
    from app.services.customer_service import CustomerService
    from app.services.dispatch_service import DispatchService
    from app.services.ticket_service import TicketService
    from app.services.tool_executor import ToolExecutor

    customer_service = CustomerService(db_session)
    tool_executor = ToolExecutor(
        customer_service=customer_service,
        dispatch_service=DispatchService(db_session),
        churn_service=ChurnService(db_session),
        ticket_service=TicketService(db_session),
        rag_retriever=AsyncMock(spec=RAGRetriever),
    )
    customer_service.get_call_context = AsyncMock(
        return_value={
            "variable_values": {"customer_name": "Guest"},
            "system_prompt_injection": "You are a helpful HVAC receptionist.",
        }
    )
    return tool_executor
