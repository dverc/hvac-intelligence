"""Tenant resolution + per-call binding."""

from __future__ import annotations

import uuid

import pytest

from app.core.constants import SEED_ORG_ID
from app.services.tenant_service import TenantService


@pytest.mark.asyncio
async def test_get_tenant_by_phone_returns_seed_for_known_number(db_session):
    service = TenantService(db_session)
    service.invalidate_cache()
    org = await service.get_tenant_by_phone("+19498800687")
    assert org.org_id == SEED_ORG_ID


@pytest.mark.asyncio
async def test_get_tenant_by_phone_falls_back_to_seed_for_unknown(db_session):
    service = TenantService(db_session)
    service.invalidate_cache()
    org = await service.get_tenant_by_phone("+15550009999")
    # Never None — falls back to the seed org.
    assert org is not None
    assert org.org_id == SEED_ORG_ID


@pytest.mark.asyncio
async def test_ttl_cache_returns_same_instance_until_invalidated(db_session):
    service = TenantService(db_session)
    service.invalidate_cache()
    first = await service.get_tenant_by_phone("+19498800687")
    second = await service.get_tenant_by_phone("+19498800687")
    assert first is second  # served from TTL cache

    service.invalidate_cache("+19498800687")
    third = await service.get_tenant_by_phone("+19498800687")
    # After invalidation the cache is repopulated from a fresh query.
    assert third.org_id == first.org_id


@pytest.mark.asyncio
async def test_resolve_org_for_call_reads_binding_then_reresolves(
    db_session, make_org, monkeypatch
):
    org_b = await make_org(name="Org B", business_phone="+15557770000")
    service = TenantService(db_session)
    service.invalidate_cache()

    # 1) Redis binding present -> use it directly (no phone needed).
    async def fake_get_bound(call_id):
        return org_b.org_id

    monkeypatch.setattr(service, "_get_bound_org", fake_get_bound)
    resolved = await service.resolve_org_for_call("call-xyz", {})
    assert resolved == org_b.org_id

    # 2) Binding absent -> re-resolve from the called number and re-cache.
    async def missing_binding(call_id):
        return None

    bound: dict[str, uuid.UUID] = {}

    async def capture_bind(call_id, org_id):
        bound[call_id] = org_id

    monkeypatch.setattr(service, "_get_bound_org", missing_binding)
    monkeypatch.setattr(service, "bind_call_org", capture_bind)

    message = {"call": {"phoneNumber": {"number": "+15557770000"}}}
    resolved2 = await service.resolve_org_for_call("call-new", message)
    assert resolved2 == org_b.org_id
    assert bound["call-new"] == org_b.org_id
