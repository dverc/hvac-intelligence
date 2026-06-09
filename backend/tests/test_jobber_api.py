from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.constants import SEED_ORG_ID
from app.core.encryption import encrypt_token
from app.models.jobber_token import JobberToken


@pytest.mark.asyncio
async def test_jobber_connect_returns_authorization_url(auth_client):
    with patch(
        "app.services.jobber_service.JobberService.get_oauth_url",
        return_value="https://api.getjobber.com/api/oauth/authorize?client_id=test",
    ):
        response = await auth_client.get("/api/v1/integrations/jobber/connect")
    assert response.status_code == 200
    assert "getjobber.com" in response.json()["authorization_url"]


@pytest.mark.asyncio
async def test_jobber_status_not_connected(auth_client):
    response = await auth_client.get("/api/v1/integrations/jobber/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False


@pytest.mark.asyncio
async def test_jobber_oauth_callback_no_api_key_redirects(api_client):
    transport = api_client._transport
    with patch(
        "app.services.jobber_service.JobberService.handle_oauth_callback",
        new_callable=AsyncMock,
    ) as mock_cb:
        mock_cb.return_value = JobberToken(
            org_id=SEED_ORG_ID,
            access_token=encrypt_token("t") or "",
            refresh_token=encrypt_token("r") or "",
            is_active=True,
        )
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/integrations/jobber/oauth/callback",
                params={"code": "abc", "state": "valid"},
                follow_redirects=False,
            )
    assert response.status_code != 401
    assert response.status_code in (302, 307)
    assert "integrations" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_jobber_sync_returns_counts(auth_client):
    with (
        patch(
            "app.services.jobber_service.JobberService.sync_clients_to_customers",
            new_callable=AsyncMock,
            return_value=2,
        ),
        patch(
            "app.services.jobber_service.JobberService.sync_users_to_technicians",
            new_callable=AsyncMock,
            return_value=1,
        ),
        patch(
            "app.services.jobber_service.JobberService.sync_jobs_to_dispatch",
            new_callable=AsyncMock,
            return_value=3,
        ),
        patch(
            "app.services.jobber_service.JobberService.mark_sync_completed",
            new_callable=AsyncMock,
        ),
    ):
        response = await auth_client.post(
            "/api/v1/integrations/jobber/sync",
            json={"sync_type": "all", "days_ahead": 7},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["clients_synced"] == 2
    assert body["users_synced"] == 1
    assert body["jobs_synced"] == 3
