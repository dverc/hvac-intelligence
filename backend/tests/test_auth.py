"""Tests for JWT user authentication endpoints."""

from __future__ import annotations

import uuid

import pytest

from app.core.constants import SEED_ORG_ID_STR


def _unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


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
async def test_login_returns_access_token(api_client):
    email = _unique_email("login")
    password = "securepass123"
    register = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "org_id": SEED_ORG_ID_STR,
        },
    )
    assert register.status_code == 201

    transport = api_client._transport
    from httpx import AsyncClient

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
async def test_login_fails_with_wrong_password(api_client):
    email = _unique_email("badpass")
    await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correctpassword",
            "org_id": SEED_ORG_ID_STR,
        },
    )

    from httpx import AsyncClient

    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": "wrongpassword"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_profile_with_valid_token(api_client):
    email = _unique_email("me")
    password = "securepass123"
    await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "org_id": SEED_ORG_ID_STR,
            "role": "read_only",
        },
    )

    from httpx import AsyncClient

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
    from httpx import AsyncClient

    transport = api_client._transport
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )

    assert response.status_code == 401
