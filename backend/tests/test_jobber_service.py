from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cryptography.fernet import Fernet

from app.core.constants import SEED_ORG_ID
from app.core.encryption import decrypt_token, encrypt_token
from app.models.customer import Customer
from app.models.jobber_token import JobberToken
from app.services.google_oauth_state import build_oauth_state, verify_oauth_state
from app.services.jobber_service import JobberService


def _httpx_json_response(url: str, payload: dict, status: int = 200) -> httpx.Response:
    request = httpx.Request("POST", url)
    return httpx.Response(status, json=payload, request=request)


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", key)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_get_oauth_url_returns_jobber_authorize_url(db_session, encryption_key):
    from app.core.config import get_settings

    settings = get_settings()
    svc = JobberService(db_session)
    url = svc.get_oauth_url(SEED_ORG_ID)
    assert "api.getjobber.com/api/oauth/authorize" in url
    assert f"client_id={settings.JOBBER_CLIENT_ID}" in url


@pytest.mark.asyncio
async def test_oauth_state_signed_and_verifiable(encryption_key, dashboard_api_key):
    state = build_oauth_state(SEED_ORG_ID, None, dashboard_api_key)
    org_id, tech_id = verify_oauth_state(state, dashboard_api_key)
    assert org_id == SEED_ORG_ID
    assert tech_id is None


@pytest.mark.asyncio
async def test_handle_oauth_callback_stores_encrypted_tokens(
    db_session, encryption_key, monkeypatch, dashboard_api_key
):
    state = build_oauth_state(SEED_ORG_ID, None, dashboard_api_key)

    async def mock_post(self, url, **kwargs):
        if "oauth/token" in url:
            return _httpx_json_response(
                url,
                {
                    "access_token": "access-jobber",
                    "refresh_token": "refresh-jobber",
                    "expires_in": 3600,
                    "scope": "read write",
                },
            )
        return _httpx_json_response(
            url,
            {"data": {"account": {"id": "acct-1", "name": "Test HVAC Co", "email": "a@b.com"}}},
        )

    with patch.object(httpx.AsyncClient, "post", mock_post):
        svc = JobberService(db_session)
        row = await svc.handle_oauth_callback("code-123", state)
        await db_session.flush()

    assert row.jobber_account_name == "Test HVAC Co"
    assert decrypt_token(row.access_token) == "access-jobber"


@pytest.mark.asyncio
async def test_handle_oauth_callback_tampered_state_raises(db_session, encryption_key, dashboard_api_key):
    state = build_oauth_state(SEED_ORG_ID, None, dashboard_api_key)
    tampered = state[:-4] + "XXXX"
    svc = JobberService(db_session)
    with pytest.raises(ValueError):
        await svc.handle_oauth_callback("code", tampered)


@pytest.mark.asyncio
async def test_graphql_query_uses_auth_header(db_session, encryption_key):
    token = JobberToken(
        org_id=SEED_ORG_ID,
        access_token=encrypt_token("tok") or "",
        refresh_token=encrypt_token("ref") or "",
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    captured: dict = {}

    async def mock_post(self, url, **kwargs):
        captured["headers"] = kwargs.get("headers") or self.headers
        return _httpx_json_response(url, {"data": {"account": {"id": "1"}}})

    with patch.object(httpx.AsyncClient, "post", mock_post):
        svc = JobberService(db_session)
        await svc.graphql_query(SEED_ORG_ID, "query { account { id } }")

    headers = captured["headers"]
    assert headers["Authorization"] == "Bearer tok"
    assert headers["X-JOBBER-GRAPHQL-VERSION"] == "2025-04-16"


@pytest.mark.asyncio
async def test_sync_clients_creates_and_updates(db_session, encryption_key):
    token = JobberToken(
        org_id=SEED_ORG_ID,
        access_token=encrypt_token("tok") or "",
        refresh_token=encrypt_token("ref") or "",
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    existing = Customer(
        org_id=SEED_ORG_ID,
        external_id="jobber:client-existing",
        full_name="Old Name",
        phone_primary="+15551112222",
        customer_since=datetime.now(timezone.utc).date(),
        account_status="ACTIVE",
        contract_type="RESIDENTIAL_OTC",
    )
    db_session.add(existing)
    await db_session.flush()

    page1 = {
        "data": {
            "clients": {
                "nodes": [
                    {
                        "id": "client-existing",
                        "firstName": "Jane",
                        "lastName": "Doe",
                        "name": "Jane Doe",
                        "emails": [{"address": "jane@example.com", "primary": True}],
                        "phones": [{"number": "+15559998888", "primary": True}],
                        "billingAddress": {
                            "street1": "1 Main",
                            "city": "LA",
                            "province": "CA",
                            "postalCode": "90001",
                        },
                    },
                    {
                        "id": "client-new",
                        "firstName": "Bob",
                        "lastName": "Smith",
                        "name": "Bob Smith",
                        "emails": [],
                        "phones": [{"number": "+15557776666", "primary": True}],
                        "billingAddress": {},
                    },
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }

    async def mock_post(self, url, **kwargs):
        return _httpx_json_response(url, page1)

    with patch.object(httpx.AsyncClient, "post", mock_post):
        svc = JobberService(db_session)
        count = await svc.sync_clients_to_customers(SEED_ORG_ID)

    assert count == 2
    await db_session.refresh(existing)
    assert existing.full_name == "Jane Doe"


@pytest.mark.asyncio
async def test_sync_users_creates_technicians(db_session, encryption_key):
    token = JobberToken(
        org_id=SEED_ORG_ID,
        access_token=encrypt_token("tok") or "",
        refresh_token=encrypt_token("ref") or "",
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    payload = {
        "data": {
            "users": {
                "nodes": [
                    {
                        "id": "user-1",
                        "name": {"first": "Alex", "last": "Tech"},
                        "email": {"raw": "alex@example.com"},
                        "status": "ACTIVE",
                    }
                ]
            }
        }
    }

    async def mock_post(self, url, **kwargs):
        return _httpx_json_response(url, payload)

    with patch.object(httpx.AsyncClient, "post", mock_post):
        svc = JobberService(db_session)
        count = await svc.sync_users_to_technicians(SEED_ORG_ID)

    assert count == 1


@pytest.mark.asyncio
async def test_create_job_in_jobber_calls_mutation(db_session, encryption_key, seeded_customer):
    from app.models.customer import Customer
    from app.models.dispatch_job import DispatchJob
    from app.models.technician import Technician

    token = JobberToken(
        org_id=SEED_ORG_ID,
        access_token=encrypt_token("tok") or "",
        refresh_token=encrypt_token("ref") or "",
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    customer = await db_session.get(
        Customer, uuid.UUID(seeded_customer["customer_id"])
    )
    customer.external_id = "jobber:client-99"
    tech = await db_session.get(
        Technician, uuid.UUID(seeded_customer["technician_id"])
    )
    tech.metadata_ = {"jobber_user_id": "user-99"}
    now = datetime.now(timezone.utc)
    job = DispatchJob(
        job_number="DX-JB-1",
        org_id=SEED_ORG_ID,
        customer_id=customer.customer_id,
        technician_id=tech.technician_id,
        issue_type="AC_NO_COOLING",
        priority="P2",
        job_status="SCHEDULED",
        issue_description="Test",
        scheduled_window_start=now,
        scheduled_window_end=now + timedelta(hours=2),
    )
    db_session.add(job)
    await db_session.flush()

    captured_body: dict = {}

    async def mock_post(self, url, **kwargs):
        captured_body.update(kwargs.get("json") or {})
        return _httpx_json_response(
            url,
            {
                "data": {
                    "jobCreate": {
                        "job": {"id": "jobber-job-1", "jobNumber": "J-100"},
                        "userErrors": [],
                    }
                }
            },
        )

    with patch.object(httpx.AsyncClient, "post", mock_post):
        svc = JobberService(db_session)
        jobber_id = await svc.create_job_in_jobber(SEED_ORG_ID, job, customer, tech)

    assert jobber_id == "jobber-job-1"
    assert captured_body["variables"]["input"]["clientId"] == "client-99"
    assert job.external_job_id == "jobber:jobber-job-1"


@pytest.mark.asyncio
async def test_create_job_in_jobber_returns_none_on_failure(
    db_session, encryption_key, seeded_customer
):
    from app.models.customer import Customer
    from app.models.dispatch_job import DispatchJob
    from app.models.technician import Technician

    token = JobberToken(
        org_id=SEED_ORG_ID,
        access_token=encrypt_token("tok") or "",
        refresh_token=encrypt_token("ref") or "",
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    customer = await db_session.get(
        Customer, uuid.UUID(seeded_customer["customer_id"])
    )
    customer.external_id = "jobber:client-99"
    tech = await db_session.get(
        Technician, uuid.UUID(seeded_customer["technician_id"])
    )
    now = datetime.now(timezone.utc)
    job = DispatchJob(
        job_number="DX-JB-2",
        org_id=SEED_ORG_ID,
        customer_id=customer.customer_id,
        technician_id=tech.technician_id,
        issue_type="AC_NO_COOLING",
        priority="P2",
        job_status="SCHEDULED",
        scheduled_window_start=now,
        scheduled_window_end=now + timedelta(hours=2),
    )
    db_session.add(job)
    await db_session.flush()

    async def mock_post(self, url, **kwargs):
        raise httpx.HTTPError("Jobber down")

    with patch.object(httpx.AsyncClient, "post", mock_post):
        svc = JobberService(db_session)
        result = await svc.create_job_in_jobber(SEED_ORG_ID, job, customer, tech)

    assert result is None


@pytest.mark.asyncio
async def test_create_client_success(db_session, encryption_key):
    token = JobberToken(
        org_id=SEED_ORG_ID,
        access_token=encrypt_token("tok") or "",
        refresh_token=encrypt_token("ref") or "",
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    customer = Customer(
        org_id=SEED_ORG_ID,
        external_id="VOICE-ABCD1234",
        full_name="Jane Newcaller",
        phone_primary="+15559998877",
        email="jane@example.com",
        address_line1="123 Main St",
        city="Irvine",
        state="CA",
        zip="92618",
        customer_since=datetime.now(timezone.utc).date(),
        account_status="ACTIVE",
        contract_type="RESIDENTIAL_OTC",
    )
    db_session.add(customer)
    await db_session.flush()

    captured_body: dict = {}

    async def mock_post(self, url, **kwargs):
        captured_body.update(kwargs.get("json") or {})
        return _httpx_json_response(
            url,
            {
                "data": {
                    "clientCreate": {
                        "client": {"id": "jobber-client-new"},
                        "userErrors": [],
                    }
                }
            },
        )

    with patch.object(httpx.AsyncClient, "post", mock_post):
        svc = JobberService(db_session)
        jobber_client_id = await svc.create_client(SEED_ORG_ID, customer)

    assert jobber_client_id == "jobber-client-new"
    client_input = captured_body["variables"]["input"]
    assert client_input["firstName"] == "Jane"
    assert client_input["lastName"] == "Newcaller"
    assert client_input["phones"][0]["number"] == "+15559998877"
    assert client_input["emails"][0]["address"] == "jane@example.com"
    assert client_input["billingAddress"]["street1"] == "123 Main St"
    assert client_input["billingAddress"]["province"] == "CA"


@pytest.mark.asyncio
async def test_create_client_returns_none_when_not_connected(db_session, encryption_key):
    customer = Customer(
        org_id=SEED_ORG_ID,
        external_id="VOICE-ABCD1234",
        full_name="Jane Newcaller",
        phone_primary="+15559998877",
        customer_since=datetime.now(timezone.utc).date(),
        account_status="ACTIVE",
        contract_type="RESIDENTIAL_OTC",
    )
    db_session.add(customer)
    await db_session.flush()

    svc = JobberService(db_session)
    assert await svc.create_client(SEED_ORG_ID, customer) is None


@pytest.mark.asyncio
async def test_create_client_returns_none_after_throttle_exhausted(
    db_session, encryption_key
):
    token = JobberToken(
        org_id=SEED_ORG_ID,
        access_token=encrypt_token("tok") or "",
        refresh_token=encrypt_token("ref") or "",
        is_active=True,
    )
    db_session.add(token)
    await db_session.flush()

    customer = Customer(
        org_id=SEED_ORG_ID,
        external_id="VOICE-ABCD1234",
        full_name="Jane Newcaller",
        phone_primary="+15559998877",
        customer_since=datetime.now(timezone.utc).date(),
        account_status="ACTIVE",
        contract_type="RESIDENTIAL_OTC",
    )
    db_session.add(customer)
    await db_session.flush()

    throttle_payload = {"errors": [{"message": "THROTTLED"}]}

    async def mock_post(self, url, **kwargs):
        return _httpx_json_response(url, throttle_payload)

    with patch.object(httpx.AsyncClient, "post", mock_post):
        with patch("app.services.jobber_service.asyncio.sleep", new_callable=AsyncMock):
            svc = JobberService(db_session)
            result = await svc.create_client(SEED_ORG_ID, customer)

    assert result is None
