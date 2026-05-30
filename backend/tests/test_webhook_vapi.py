import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import sign_vapi_payload


@pytest.mark.asyncio
async def test_valid_hmac_signature_passes(api_client):
    payload = {"message": {"type": "status-update", "call": {"id": "c1"}}}
    body, signature = sign_vapi_payload(payload)
    response = await api_client.post(
        "/webhook/vapi",
        content=body,
        headers={"x-vapi-signature": signature, "content-type": "application/json"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_signature_returns_401(api_client):
    payload = {"message": {"type": "call-start", "call": {"id": "c2"}}}
    body = json.dumps(payload).encode("utf-8")
    response = await api_client.post(
        "/webhook/vapi",
        content=body,
        headers={"x-vapi-signature": "sha256=deadbeef", "content-type": "application/json"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_call_start_high_risk_injects_retention(db_session, seeded_customer, monkeypatch):
    from app.api import deps
    from app.main import app
    from app.pipeline import event_bus
    from app.rag.retriever import RAGRetriever
    from app.services.churn_service import ChurnService
    from app.services.customer_service import CustomerService
    from app.services.dispatch_service import DispatchService
    from app.services.ticket_service import TicketService
    from app.services.tool_executor import ToolExecutor
    from httpx import ASGITransport, AsyncClient

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
    app.dependency_overrides[deps.get_tool_executor] = lambda: tool_executor

    payload = {
        "message": {
            "type": "call-start",
            "call": {
                "id": "call-high-risk",
                "customer": {"number": seeded_customer["phone"]},
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
    data = response.json()
    prompt = data["assistant"]["model"]["systemPrompt"]
    assert "HIGH" in prompt or "CHURN RISK" in prompt
    assert "retention" in prompt.lower() or "Retention" in prompt


@pytest.mark.asyncio
async def test_tool_calls_routes_to_handlers(api_client, mock_tool_executor):
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {"id": "call-tools"},
            "toolCallList": [
                {"id": "tc1", "name": "query_churn_score", "arguments": {"customer_id": "x"}},
            ],
        }
    }
    body, signature = sign_vapi_payload(payload)
    response = await api_client.post(
        "/webhook/vapi",
        content=body,
        headers={"x-vapi-signature": signature, "content-type": "application/json"},
    )
    assert response.status_code == 200
    assert mock_tool_executor.calls
    assert mock_tool_executor.calls[0][0] == "query_churn_score"


@pytest.mark.asyncio
async def test_call_end_triggers_background_transcript(api_client):
    with patch("app.api.v1.webhook_vapi._process_call_end_background") as mock_bg:
        payload = {
            "message": {
                "type": "call-end",
                "call": {"id": "call-end-1", "customer": {"number": "+15552001001"}},
            }
        }
        body, signature = sign_vapi_payload(payload)
        response = await api_client.post(
            "/webhook/vapi",
            content=body,
            headers={"x-vapi-signature": signature, "content-type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
        mock_bg.assert_called_once()
