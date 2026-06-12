"""Admin organization onboarding API tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import SEED_ORG_ID_STR
from app.core.config import get_settings
from app.models.org_settings import OrgSettings
from app.models.organization import Organization
from app.models.user import User
from app.services.admin_onboarding_service import AdminOnboardingService


async def _create_dispatcher_user(db_session: AsyncSession) -> tuple[str, str]:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    email = f"dispatcher-{uuid.uuid4().hex[:8]}@test.local"
    password = "TestDispatcherPass123!"
    user = User(
        org_id=SEED_ORG_ID_STR,
        email=email,
        hashed_password=pwd_context.hash(password),
        role="dispatcher",
    )
    db_session.add(user)
    await db_session.flush()
    return email, password


@pytest_asyncio.fixture
async def dispatcher_client(
    db_session: AsyncSession,
    api_client: AsyncClient,
) -> AsyncClient:
    """JWT client for a non-admin dispatcher user."""
    from app.core.rate_limit import limiter

    email, password = await _create_dispatcher_user(db_session)
    transport = api_client._transport
    limiter.enabled = False
    try:
        login_resp = await api_client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )
    finally:
        limiter.enabled = True
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]

    settings = get_settings()
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-API-Key": settings.DASHBOARD_API_KEY,
            "Authorization": f"Bearer {token}",
        },
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_admin_can_list_organizations(auth_client):
    response = await auth_client.get("/api/v1/admin/organizations")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(item["org_id"] == SEED_ORG_ID_STR for item in data)


@pytest.mark.asyncio
async def test_non_admin_cannot_list_organizations(dispatcher_client):
    response = await dispatcher_client.get("/api/v1/admin/organizations")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_organizations_uses_single_query(db_session, make_org):
    for idx in range(3):
        org = await make_org(name=f"List Query Org {idx}")
        db_session.add(
            OrgSettings(
                org_id=org.org_id,
                display_name=org.org_name,
                onboarding_step=idx,
            )
        )
    await db_session.flush()

    mock_execute = AsyncMock(wraps=db_session.execute)
    with patch.object(db_session, "execute", mock_execute):
        items = await AdminOnboardingService(db_session).list_organizations()

    assert mock_execute.await_count == 1
    assert len(items) >= 4


@pytest.mark.asyncio
async def test_admin_can_create_organization(auth_client):
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "company_name": f"Desert Air HVAC {suffix}",
        "admin_email": f"admin-{suffix}@example.com",
        "admin_first_name": "Jane",
        "admin_last_name": "Smith",
    }
    response = await auth_client.post("/api/v1/admin/organizations", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["org_name"] == payload["company_name"]
    assert body["settings"]["display_name"] == payload["company_name"]
    assert body["temporary_password"]
    assert body["admin_user_id"]


@pytest.mark.asyncio
async def test_admin_can_create_user_for_org(auth_client, db_session):
    suffix = uuid.uuid4().hex[:8]
    create_resp = await auth_client.post(
        "/api/v1/admin/organizations",
        json={
            "company_name": f"Valley Cool {suffix}",
            "admin_email": f"owner-{suffix}@example.com",
        },
    )
    assert create_resp.status_code == 201
    org_id = create_resp.json()["org_id"]

    user_resp = await auth_client.post(
        f"/api/v1/admin/organizations/{org_id}/users",
        json={
            "email": f"dispatcher-{suffix}@example.com",
            "first_name": "Bob",
            "last_name": "Tech",
            "role": "dispatcher",
        },
    )
    assert user_resp.status_code == 201
    user_body = user_resp.json()
    assert user_body["email"] == f"dispatcher-{suffix}@example.com"
    assert user_body["role"] == "dispatcher"
    assert user_body["org_id"] == org_id
    assert len(user_body["temporary_password"]) >= 8


@pytest.mark.asyncio
async def test_onboarding_step_updates_correctly(auth_client):
    suffix = uuid.uuid4().hex[:8]
    create_resp = await auth_client.post(
        "/api/v1/admin/organizations",
        json={
            "company_name": f"Onboard Test {suffix}",
            "admin_email": f"onboard-{suffix}@example.com",
        },
    )
    org_id = create_resp.json()["org_id"]

    patch_resp = await auth_client.patch(
        f"/api/v1/admin/organizations/{org_id}/onboarding",
        json={"onboarding_step": 3},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["onboarding_step"] == 3
    assert patch_resp.json()["onboarding_completed"] is False

    complete_resp = await auth_client.patch(
        f"/api/v1/admin/organizations/{org_id}/onboarding",
        json={"onboarding_completed": True},
    )
    assert complete_resp.status_code == 200
    body = complete_resp.json()
    assert body["onboarding_completed"] is True
    assert body["onboarding_step"] >= 5


@pytest.mark.asyncio
async def test_provision_endpoint_creates_org_settings(auth_client, db_session):
    org = Organization(
        org_name=f"Provision Co {uuid.uuid4().hex[:6]}",
        slug=f"provision-{uuid.uuid4().hex[:8]}",
        industry="hvac",
        plan_tier="starter",
        is_active=True,
        settings={},
    )
    db_session.add(org)
    await db_session.flush()

    settings_before = (
        await db_session.execute(
            select(OrgSettings).where(OrgSettings.org_id == org.org_id)
        )
    ).scalar_one_or_none()
    assert settings_before is None

    response = await auth_client.post(
        f"/api/v1/admin/organizations/{org.org_id}/provision"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["org_id"] == str(org.org_id)
    assert body["settings"]["onboarding_step"] >= 1
    assert body["settings"]["agent_greeting"]

    settings_after = (
        await db_session.execute(
            select(OrgSettings).where(OrgSettings.org_id == org.org_id)
        )
    ).scalar_one_or_none()
    assert settings_after is not None
