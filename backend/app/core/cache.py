"""Redis cache helpers for hot read paths during live calls."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CUSTOMER_CACHE_TTL = 300
ORG_CACHE_TTL = 900
RAG_CHUNKS_CACHE_TTL = 86400

_redis_client: Any | None = None


def get_redis_client() -> Any:
    """Return a shared async Redis client."""
    global _redis_client
    if _redis_client is None:
        from redis.asyncio import Redis

        _redis_client = Redis.from_url(
            get_settings().REDIS_URL,
            decode_responses=True,
        )
    return _redis_client


def customer_cache_key(org_id: str, phone: str) -> str:
    return f"customer:{org_id}:{phone}"


def org_cache_key(org_id: str) -> str:
    return f"org:{org_id}:settings"


def rag_chunks_cache_key(call_id: str) -> str:
    return f"rag_chunks:{call_id}"


async def cache_get(key: str) -> dict | None:
    try:
        raw = await get_redis_client().get(key)
        if raw is None:
            return None
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
        return None
    except Exception:
        logger.debug("cache_get failed for key=%s", key, exc_info=True)
        return None


async def cache_set(key: str, value: dict, ttl_seconds: int) -> None:
    try:
        await get_redis_client().set(key, json.dumps(value), ex=ttl_seconds)
    except Exception:
        logger.debug("cache_set failed for key=%s", key, exc_info=True)


async def cache_delete(key: str) -> None:
    try:
        await get_redis_client().delete(key)
    except Exception:
        logger.debug("cache_delete failed for key=%s", key, exc_info=True)
