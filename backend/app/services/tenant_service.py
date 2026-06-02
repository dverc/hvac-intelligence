"""Tenant resolution + per-call org binding.

Tenant isolation is a SECURITY boundary. The org for a call is resolved at
call-start from the *called* business number and bound to the call_id in Redis
so later webhook events (tool-calls, end-of-call-report) — which may not carry
the called number — resolve the same tenant. Resolution NEVER returns None for
phone lookups; it falls back to the seed org so a write always has a valid org.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from typing import Any, Optional

from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import SEED_ORG_ID
from app.models.organization import Organization

logger = logging.getLogger(__name__)

# Module-level cache shared across requests/instances. Guarded by a lock for
# thread safety (cachetools is not thread-safe on its own).
_PHONE_CACHE: TTLCache[str, Organization] = TTLCache(maxsize=512, ttl=60)
_CACHE_LOCK = threading.Lock()

_CALL_ORG_TTL_SECONDS = 7200
_CALL_ORG_KEY = "call_org:{call_id}"


def normalize_phone(phone: str | None) -> str:
    """Strip spaces/punctuation and ensure a leading '+'. Empty stays empty."""
    if not phone:
        return ""
    stripped = phone.strip()
    digits = re.sub(r"\D", "", stripped)
    if not digits:
        return ""
    if len(digits) == 10:
        return f"+1{digits}"
    return f"+{digits}"


class TenantService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Resolution ──────────────────────────────────────────────────────────

    async def get_tenant_by_phone(self, called_number: str | None) -> Organization:
        """Resolve a tenant by its inbound business number. Never returns None."""
        normalized = normalize_phone(called_number)

        if normalized:
            with _CACHE_LOCK:
                cached = _PHONE_CACHE.get(normalized)
            if cached is not None:
                return cached

            stmt = select(Organization).where(
                Organization.business_phone == normalized,
                Organization.is_active.is_(True),
            )
            org = (await self.db.execute(stmt)).scalar_one_or_none()
            if org is not None:
                with _CACHE_LOCK:
                    _PHONE_CACHE[normalized] = org
                return org

        # Fail-safe: fall back to the seed org so a write always has a tenant.
        seed = await self.get_tenant_by_id(SEED_ORG_ID)
        if seed is None:
            raise RuntimeError(
                "Seed organization is missing; run migration 005 before serving calls."
            )
        return seed

    async def get_tenant_by_id(self, org_id: uuid.UUID) -> Optional[Organization]:
        return await self.db.get(Organization, org_id)

    async def get_all_active_tenants(self) -> list[Organization]:
        stmt = select(Organization).where(Organization.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    def invalidate_cache(self, phone: str | None = None) -> None:
        with _CACHE_LOCK:
            if phone is None:
                _PHONE_CACHE.clear()
            else:
                _PHONE_CACHE.pop(normalize_phone(phone), None)

    # ── Per-call org binding (read-through via Redis) ────────────────────────

    async def resolve_org_for_call(
        self, call_id: str, message: dict[str, Any]
    ) -> uuid.UUID:
        """Return the org_id for this call.

        Reads the call->org binding from Redis. If absent (e.g. server restarted
        mid-call, or this is the first event), re-resolves from the called number
        and re-caches the binding.
        """
        if call_id:
            bound = await self._get_bound_org(call_id)
            if bound is not None:
                return bound

        called_number = _extract_called_number(message)
        org = await self.get_tenant_by_phone(called_number)
        if call_id:
            await self.bind_call_org(call_id, org.org_id)
        return org.org_id

    async def bind_call_org(self, call_id: str, org_id: uuid.UUID) -> None:
        await self._set_bound_org(call_id, org_id)

    async def _get_bound_org(self, call_id: str) -> Optional[uuid.UUID]:
        try:
            from redis.asyncio import Redis

            client = Redis.from_url(get_settings().REDIS_URL, decode_responses=True)
            try:
                raw = await client.get(_CALL_ORG_KEY.format(call_id=call_id))
            finally:
                await client.aclose()
            if raw:
                return uuid.UUID(raw)
        except Exception as exc:  # pragma: no cover - redis optional in dev
            logger.warning("Redis read for call_org binding failed: %s", exc)
        return None

    async def _set_bound_org(self, call_id: str, org_id: uuid.UUID) -> None:
        try:
            from redis.asyncio import Redis

            client = Redis.from_url(get_settings().REDIS_URL, decode_responses=True)
            try:
                await client.set(
                    _CALL_ORG_KEY.format(call_id=call_id),
                    str(org_id),
                    ex=_CALL_ORG_TTL_SECONDS,
                )
            finally:
                await client.aclose()
        except Exception as exc:  # pragma: no cover - redis optional in dev
            logger.warning("Redis write for call_org binding failed: %s", exc)


def _extract_called_number(message: dict[str, Any]) -> Optional[str]:
    """Best-effort extraction of the *called* (business) number from a webhook.

    Order: call.phoneNumber.number, message.phoneNumber.number, call.to,
    message.phoneNumberId map (not maintained), then VAPI_PHONE_NUMBER fallback.
    """
    call = message.get("call") or {}

    phone_number = call.get("phoneNumber") or message.get("phoneNumber")
    if isinstance(phone_number, dict) and phone_number.get("number"):
        return str(phone_number["number"])
    if isinstance(phone_number, str) and phone_number:
        return phone_number

    to = call.get("to") or message.get("to")
    if isinstance(to, str) and to:
        return to

    fallback = get_settings().VAPI_PHONE_NUMBER
    return fallback or None
