"""Tests for JWT user authentication endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_jwt import ALGORITHM, create_access_token
from app.core.config import get_settings
from app.core.constants import SEED_ORG_ID_STR
from app.models.user import User


def _unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_test_user(
    api_client,
    db_session: AsyncSession,
    email: str,
    password: str,
    *,
    role: str = "dispatcher",
) -> None:
    """Register via POST /auth/register (X-API-Key) or seed user if JWT blocks register."""
    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "org_id": SEED_ORG_ID_STR,
            "role": role,
        },
    )
    if response.status_code == 201:
        return

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        org_id=SEED_ORG_ID_STR,
        email=email,
        hashed_password=pwd_context.hash(password),
        role=role,
    )
    db_session.add(user)
    await db_session.flush()


@pytest.mark.asyncio
async def test_register_creates_user(api_client):
    email = _unique_email("register")
    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "securepass123",
            "org_id": SEED_ORG_ID_STR,
            "role": "dispatcher",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["role"] == "dispatcher"
    assert body["org_id"] == SEED_ORG_ID_STR
    assert body["user_id"]


@pytest.mark.asyncio
async def test_login_returns_access_token(api_client, db_session):
    email = _unique_email("login")
    password = "securepass123"
    await _register_test_user(api_client, db_session, email, password)

    transport = api_client._transport

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["email"] == email
    assert body["user_id"]
    assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_fails_with_wrong_password(api_client, db_session):
    email = _unique_email("badpass")
    await _register_test_user(api_client, db_session, email, "correctpassword")

    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": "wrongpassword"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_profile_with_valid_token(api_client, db_session):
    email = _unique_email("me")
    password = "securepass123"
    await _register_test_user(
        api_client, db_session, email, password, role="read_only"
    )

    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )
        token = login.json()["access_token"]
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == email
    assert body["role"] == "read_only"
    assert body["org_id"] == SEED_ORG_ID_STR
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_me_returns_401_with_invalid_token(api_client):
    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_returns_200_for_unknown_email(api_client):
    response = await api_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": _unique_email("unknown")},
    )
    assert response.status_code == 200
    assert response.json()["message"] == (
        "If that email is registered, you will receive a reset link"
    )


@pytest.mark.asyncio
async def test_forgot_password_returns_200_for_registered_email(api_client, db_session):
    email = _unique_email("forgot")
    await _register_test_user(api_client, db_session, email, "securepass123")

    with patch("app.api.v1.auth.send_email", return_value=True) as mock_send:
        response = await api_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": email},
        )

    assert response.status_code == 200
    assert response.json()["message"] == (
        "If that email is registered, you will receive a reset link"
    )
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_reset_password_succeeds_with_valid_token(api_client, db_session):
    email = _unique_email("reset")
    password = "securepass123"
    new_password = "newsecurepass456"
    await _register_test_user(api_client, db_session, email, password)
    token = create_access_token(
        {"sub": email, "type": "password_reset"},
        expires_minutes=60,
    )

    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": new_password},
        )
        login = await client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": new_password},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Password updated"
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_fails_with_invalid_token(api_client):
    response = await api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-valid-token", "new_password": "newsecurepass456"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_fails_with_expired_token(api_client, db_session):
    email = _unique_email("expired-reset")
    await _register_test_user(api_client, db_session, email, "securepass123")
    settings = get_settings()
    expired_payload = {
        "sub": email,
        "type": "password_reset",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = jwt.encode(expired_payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)

    response = await api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "newsecurepass456"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_rate_limit_returns_429(api_client):
    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        responses = []
        for index in range(6):
            response = await client.post(
                "/api/v1/auth/login",
                data={
                    "username": f"ratelimit-{index}@example.com",
                    "password": "wrongpassword",
                },
            )
            responses.append(response)

    assert responses[-1].status_code == 429


@pytest.mark.asyncio
async def test_login_locks_account_after_five_failed_attempts(api_client, db_session):
    from app.core.rate_limit import limiter

    email = _unique_email("lockout")
    password = "securepass123"
    await _register_test_user(api_client, db_session, email, password)

    limiter.enabled = False
    try:
        transport = api_client._transport
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(5):
                failed = await client.post(
                    "/api/v1/auth/login",
                    data={"username": email, "password": "wrongpassword"},
                )
                assert failed.status_code == 401

            locked = await client.post(
                "/api/v1/auth/login",
                data={"username": email, "password": password},
            )
    finally:
        limiter.enabled = True

    assert locked.status_code == 423
    assert locked.json()["detail"] == "Account temporarily locked. Try again later."


@pytest.mark.asyncio
async def test_me_returns_401_with_expired_access_token(api_client, db_session):
    email = _unique_email("expired-access")
    await _register_test_user(api_client, db_session, email, "securepass123")
    settings = get_settings()
    expired_payload = {
        "sub": email,
        "email": email,
        "role": "dispatcher",
        "org_id": SEED_ORG_ID_STR,
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = jwt.encode(expired_payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)

    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_401_with_missing_token(api_client):
    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_lockout_expires_after_fifteen_minutes(api_client, db_session):
    from app.core.constants import LOCKOUT_MINUTES
    from app.core.rate_limit import limiter

    email = _unique_email("lockout-expiry")
    password = "securepass123"
    await _register_test_user(api_client, db_session, email, password)

    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    user.failed_login_attempts = 5
    user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.flush()

    limiter.enabled = False
    try:
        transport = api_client._transport
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": email, "password": password},
            )
    finally:
        limiter.enabled = True

    assert response.status_code == 200
    assert LOCKOUT_MINUTES == 15


@pytest.mark.asyncio
async def test_locked_account_returns_423(api_client, db_session):
    from app.core.rate_limit import limiter

    email = _unique_email("locked423")
    await _register_test_user(api_client, db_session, email, "securepass123")

    limiter.enabled = False
    try:
        transport = api_client._transport
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(5):
                await client.post(
                    "/api/v1/auth/login",
                    data={"username": email, "password": "wrongpassword"},
                )
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": email, "password": "wrongpassword"},
            )
    finally:
        limiter.enabled = True

    assert response.status_code == 423
