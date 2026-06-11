"""Tests for dashboard API authentication."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import sign_vapi_payload

_UNAUTHORIZED_DETAILS = {
    "Invalid or missing API key",
    "Not authenticated",
    "Invalid or expired token",
}


@pytest.mark.asyncio
async def test_customers_without_api_key_returns_401(api_client):
    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/customers")
    assert response.status_code == 401
    assert response.json()["detail"] in _UNAUTHORIZED_DETAILS


@pytest.mark.asyncio
async def test_customers_with_wrong_api_key_returns_401(api_client):
    transport = api_client._transport
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": "wrong-key"},
    ) as client:
        response = await client.get("/api/v1/customers")
    assert response.status_code == 401
    assert response.json()["detail"] in _UNAUTHORIZED_DETAILS


@pytest.mark.asyncio
async def test_customers_with_api_key_but_no_jwt_returns_401(api_client, dashboard_api_key):
    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/customers",
            headers={"X-API-Key": dashboard_api_key},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_customers_with_correct_api_key_returns_200(auth_client, seeded_customer):
    response = await auth_client.get("/api/v1/customers")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body


@pytest.mark.asyncio
async def test_health_without_api_key_returns_200(api_client):
    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_without_api_key_not_rejected_by_api_key_auth(api_client):
    payload = {"message": {"type": "status-update", "call": {"id": "auth-test-1"}}}
    body, signature = sign_vapi_payload(payload)
    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhook/vapi",
            content=body,
            headers={
                "x-vapi-signature": signature,
                "content-type": "application/json",
            },
        )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
