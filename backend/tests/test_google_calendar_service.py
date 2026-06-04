from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials

from app.core.constants import SEED_ORG_ID
from app.core.encryption import decrypt_token, encrypt_token
from app.models.google_calendar_token import GoogleCalendarToken
from app.services.google_calendar_service import GoogleCalendarService
from app.services.google_oauth_state import OAuthStateError, build_oauth_state, verify_oauth_state


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", key)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_get_oauth_url_returns_google_auth_url(db_session, encryption_key):
    svc = GoogleCalendarService(db_session)
    url = svc.get_oauth_url(SEED_ORG_ID)
    assert "accounts.google.com" in url
    assert "client_id=test-google-client-id" in url or "client_id=" in url


@pytest.mark.asyncio
async def test_oauth_state_signed_and_verifiable(db_session, encryption_key):
    tech_id = uuid.uuid4()
    state = build_oauth_state(SEED_ORG_ID, tech_id, "test-api-key-for-tests")
    org, tech = verify_oauth_state(state, "test-api-key-for-tests")
    assert org == SEED_ORG_ID
    assert tech == tech_id


@pytest.mark.asyncio
async def test_handle_oauth_callback_stores_encrypted_tokens(
    db_session, encryption_key, monkeypatch
):
    state = build_oauth_state(SEED_ORG_ID, None, "test-api-key-for-tests")
    mock_creds = Credentials(
        token="access-xyz",
        refresh_token="refresh-xyz",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-google-client-id.apps.googleusercontent.com",
        client_secret="test-google-secret",
    )

    mock_flow = MagicMock()
    mock_flow.credentials = mock_creds
    mock_flow.fetch_token = MagicMock()

    with (
        patch(
            "app.services.google_calendar_service.Flow.from_client_config",
            return_value=mock_flow,
        ),
        patch.object(
            GoogleCalendarService,
            "_resolve_account_email",
            return_value="owner@example.com",
        ),
    ):
        svc = GoogleCalendarService(db_session)
        row = await svc.handle_oauth_callback("auth-code", state)
        await db_session.flush()

    assert row.google_account_email == "owner@example.com"
    assert row.access_token != "access-xyz"
    assert decrypt_token(row.access_token) == "access-xyz"


@pytest.mark.asyncio
async def test_handle_oauth_callback_tampered_state_raises(db_session, encryption_key):
    state = build_oauth_state(SEED_ORG_ID, None, "test-api-key-for-tests")
    tampered = state[:-4] + "XXXX"
    svc = GoogleCalendarService(db_session)
    with pytest.raises(ValueError, match="signature|Invalid|mismatch"):
        await svc.handle_oauth_callback("code", tampered)


@pytest.mark.asyncio
async def test_handle_oauth_callback_expired_state_raises(db_session, encryption_key):
    old_ts = int(time.time()) - 700
    state = build_oauth_state(
        SEED_ORG_ID, None, "test-api-key-for-tests", timestamp=old_ts
    )
    with pytest.raises(OAuthStateError, match="expired"):
        verify_oauth_state(state, "test-api-key-for-tests")


@pytest.mark.asyncio
async def test_get_calendar_service_refreshes_expired_token(
    db_session, encryption_key
):
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    row = GoogleCalendarToken(
        org_id=SEED_ORG_ID,
        google_account_email="tech@example.com",
        calendar_id="primary",
        access_token=encrypt_token("old-access") or "",
        refresh_token=encrypt_token("refresh-token"),
        token_expiry=expired,
        is_active=True,
    )
    db_session.add(row)
    await db_session.flush()

    creds = MagicMock()
    creds.expired = True
    creds.refresh_token = "refresh-token"
    creds.token = "old-access"
    creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_service = MagicMock()

    def fake_refresh(request):
        creds.token = "new-access"

    creds.refresh = MagicMock(side_effect=fake_refresh)

    with (
        patch.object(GoogleCalendarService, "_build_credentials", return_value=creds),
        patch(
            "app.services.google_calendar_service.build",
            return_value=mock_service,
        ),
    ):
        svc = GoogleCalendarService(db_session)
        service, _ = await svc.get_calendar_service(SEED_ORG_ID)
        assert service is mock_service

    await db_session.refresh(row)
    assert decrypt_token(row.access_token) == "new-access"


@pytest.mark.asyncio
async def test_create_calendar_event_payload(db_session, encryption_key, seeded_customer):
    row = GoogleCalendarToken(
        org_id=SEED_ORG_ID,
        technician_id=uuid.UUID(seeded_customer["technician_id"]),
        google_account_email="cal@example.com",
        calendar_id="primary",
        access_token=encrypt_token("tok") or "",
        refresh_token=encrypt_token("ref"),
        is_active=True,
    )
    db_session.add(row)
    await db_session.flush()

    mock_events = MagicMock()
    mock_events.insert.return_value.execute.return_value = {"id": "evt-123"}
    mock_service = MagicMock()
    mock_service.events.return_value = mock_events

    from app.models.customer import Customer
    from app.models.dispatch_job import DispatchJob
    from app.models.technician import Technician

    customer = await db_session.get(
        Customer, uuid.UUID(seeded_customer["customer_id"])
    )
    tech = await db_session.get(
        Technician, uuid.UUID(seeded_customer["technician_id"])
    )
    now = datetime.now(timezone.utc)
    job = DispatchJob(
        job_number="DX-GCAL-1",
        org_id=SEED_ORG_ID,
        customer_id=customer.customer_id,
        technician_id=tech.technician_id,
        issue_type="AC_FAILURE",
        priority="P1",
        job_status="SCHEDULED",
        issue_description="No cool air",
        scheduled_window_start=now,
        scheduled_window_end=now + timedelta(hours=2),
    )
    db_session.add(job)
    await db_session.flush()

    with patch.object(
        GoogleCalendarService,
        "get_calendar_service",
        return_value=(mock_service, row),
    ):
        with patch.object(
            GoogleCalendarService, "_org_timezone", return_value="America/Los_Angeles"
        ):
            svc = GoogleCalendarService(db_session)
            event_id = await svc.create_calendar_event(
                SEED_ORG_ID, job, tech, customer
            )

    assert event_id == "evt-123"
    body = mock_events.insert.call_args.kwargs["body"]
    assert "AC_FAILURE" in body["summary"]
    assert body["colorId"] == "11"
    assert "Job: DX-GCAL-1" in body["description"]


@pytest.mark.asyncio
async def test_sync_calendar_creates_overrides_for_external_events(
    db_session, encryption_key, seeded_customer
):
    tech_id = uuid.UUID(seeded_customer["technician_id"])
    row = GoogleCalendarToken(
        org_id=SEED_ORG_ID,
        technician_id=tech_id,
        google_account_email="cal@example.com",
        calendar_id="primary",
        access_token=encrypt_token("tok") or "",
        is_active=True,
    )
    db_session.add(row)
    await db_session.flush()

    mock_events = MagicMock()
    mock_events.list.return_value.execute.return_value = {
        "items": [
            {
                "summary": "Dentist",
                "description": "Personal appointment",
                "start": {"date": str(date.today() + timedelta(days=1))},
            },
            {
                "summary": "Our dispatch",
                "description": "Job: DX-9999\nCustomer: Test",
                "start": {
                    "dateTime": (
                        datetime.now(timezone.utc) + timedelta(days=2)
                    ).isoformat()
                },
                "end": {
                    "dateTime": (
                        datetime.now(timezone.utc) + timedelta(days=2, hours=1)
                    ).isoformat()
                },
            },
        ]
    }
    mock_service = MagicMock()
    mock_service.events.return_value = mock_events

    with patch.object(
        GoogleCalendarService,
        "get_calendar_service",
        return_value=(mock_service, row),
    ):
        with patch.object(
            GoogleCalendarService, "_org_timezone", return_value="UTC"
        ):
            svc = GoogleCalendarService(db_session)
            count = await svc.sync_calendar_to_availability(
                SEED_ORG_ID,
                tech_id,
                date.today(),
                date.today() + timedelta(days=7),
            )

    assert count == 1
