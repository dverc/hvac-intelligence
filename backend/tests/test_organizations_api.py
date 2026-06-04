"""Organizations REST API."""

from __future__ import annotations

import uuid

import pytest


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_create_organization_succeeds(api_client):
    slug = _unique("acme")
    phone = f"+1555{uuid.uuid4().int % 100000000:08d}"
    response = await api_client.post(
        "/api/v1/organizations",
        json={
            "org_name": "Acme Plumbing",
            "slug": slug,
            "industry": "plumbing",
            "business_phone": phone,
            "settings": {"pinecone_namespace": "faq_general"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == slug
    assert body["industry"] == "plumbing"
    assert body["settings"]["pinecone_namespace"] == "faq_general"


@pytest.mark.asyncio
async def test_create_organization_slug_stored(api_client):
    slug = _unique("plumb-co")
    response = await api_client.post(
        "/api/v1/organizations",
        json={
            "org_name": "Plumb Co",
            "slug": slug,
            "industry": "plumbing",
        },
    )
    assert response.status_code == 201
    assert response.json()["slug"] == slug


@pytest.mark.asyncio
async def test_create_organization_rejects_duplicate_slug(api_client):
    slug = _unique("dup")
    payload = {"org_name": "First", "slug": slug, "industry": "hvac"}
    first = await api_client.post("/api/v1/organizations", json=payload)
    assert first.status_code == 201

    payload["org_name"] = "Second"
    dup = await api_client.post("/api/v1/organizations", json=payload)
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_create_organization_rejects_duplicate_phone(api_client):
    phone = f"+1555{uuid.uuid4().int % 100000000:08d}"
    a = await api_client.post(
        "/api/v1/organizations",
        json={
            "org_name": "A",
            "slug": _unique("a"),
            "industry": "hvac",
            "business_phone": phone,
        },
    )
    assert a.status_code == 201
    b = await api_client.post(
        "/api/v1/organizations",
        json={
            "org_name": "B",
            "slug": _unique("b"),
            "industry": "hvac",
            "business_phone": phone,
        },
    )
    assert b.status_code == 409


@pytest.mark.asyncio
async def test_list_and_get_organization(api_client):
    slug = _unique("listme")
    created = await api_client.post(
        "/api/v1/organizations",
        json={"org_name": "ListMe", "slug": slug, "industry": "electrical"},
    )
    org_id = created.json()["org_id"]

    listing = await api_client.get("/api/v1/organizations")
    assert listing.status_code == 200
    assert any(o["org_id"] == org_id for o in listing.json())

    one = await api_client.get(f"/api/v1/organizations/{org_id}")
    assert one.status_code == 200
    assert one.json()["slug"] == slug


@pytest.mark.asyncio
async def test_get_unknown_organization_returns_404(api_client):
    response = await api_client.get(f"/api/v1/organizations/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_deep_merges_settings(api_client):
    slug = _unique("merge")
    created = await api_client.post(
        "/api/v1/organizations",
        json={
            "org_name": "Merge Co",
            "slug": slug,
            "industry": "hvac",
            "settings": {
                "pinecone_namespace": "ns-1",
                "issue_taxonomy": ["A", "B"],
                "timezone": "America/Los_Angeles",
            },
        },
    )
    org_id = created.json()["org_id"]

    patched = await api_client.patch(
        f"/api/v1/organizations/{org_id}",
        json={"settings": {"timezone": "America/New_York", "first_message": "Hi!"}},
    )
    assert patched.status_code == 200
    settings = patched.json()["settings"]
    # Deep-merge: existing keys preserved, patched keys overridden/added.
    assert settings["pinecone_namespace"] == "ns-1"
    assert settings["issue_taxonomy"] == ["A", "B"]
    assert settings["timezone"] == "America/New_York"
    assert settings["first_message"] == "Hi!"
