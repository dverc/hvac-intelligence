from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.constants import SEED_ORG_ID
from app.core.encryption import encrypt_token
from app.models.google_calendar_token import GoogleCalendarToken


@pytest.mark.asyncio
async def test_google_connect_returns_authorization_url(auth_client):
    with patch(
        "app.services.google_calendar_service.GoogleCalendarService.get_oauth_url",
        return_value="https://accounts.google.com/o/oauth2/auth?client_id=test",
    ):
        response = await auth_client.get("/api/v1/integrations/google/connect")
    assert response.status_code == 200
    assert "accounts.google.com" in response.json()["authorization_url"]


@pytest.mark.asyncio
async def test_google_status_not_connected(auth_client):
    response = await auth_client.get("/api/v1/integrations/google/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["calendars"] == []


@pytest.mark.asyncio
async def test_google_oauth_callback_no_api_key_redirects(api_client):
    transport = api_client._transport
    with patch(
        "app.services.google_calendar_service.GoogleCalendarService.handle_oauth_callback",
        new_callable=AsyncMock,
    ) as mock_cb:
        mock_cb.return_value = GoogleCalendarToken(
            org_id=SEED_ORG_ID,
            google_account_email="u@example.com",
            calendar_id="primary",
            access_token=encrypt_token("t") or "",
            is_active=True,
        )
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/integrations/google/oauth/callback",
                params={"code": "abc", "state": "valid-state"},
                follow_redirects=False,
            )
    assert response.status_code != 401
    assert response.status_code in (302, 307)
    assert "integrations" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_google_sync_returns_count(auth_client, db_session, encryption_key):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    import os

    os.environ["GOOGLE_TOKEN_ENCRYPTION_KEY"] = key
    from app.core.config import get_settings

    get_settings.cache_clear()

    tech_id = uuid.uuid4()
    with patch(
        "app.services.google_calendar_service.GoogleCalendarService.sync_calendar_to_availability",
        new_callable=AsyncMock,
        return_value=3,
    ):
        response = await auth_client.post(
            "/api/v1/integrations/google/sync",
            json={
                "technician_id": str(tech_id),
                "date_from": "2026-06-01",
                "date_to": "2026-06-14",
            },
        )
    assert response.status_code == 200
    assert response.json()["synced"] == 3


@pytest.fixture
def encryption_key(monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", key)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()
