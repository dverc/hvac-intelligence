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


async def cache_rpush_json_items(
    key: str,
    items: list[dict[str, Any]],
    ttl_seconds: int,
) -> None:
    """Atomically append JSON objects to a Redis list (safe for concurrent writers)."""
    if not items:
        return
    try:
        client = get_redis_client()
        key_type = await client.type(key)
        if key_type in {"string", b"string"}:
            raw = await client.get(key)
            await client.delete(key)
            if raw:
                try:
                    legacy = json.loads(raw)
                    if isinstance(legacy, dict):
                        for chunk in legacy.get("chunks") or []:
                            if isinstance(chunk, dict):
                                await client.rpush(key, json.dumps(chunk))
                except json.JSONDecodeError:
                    pass
        for item in items:
            await client.rpush(key, json.dumps(item))
        await client.expire(key, ttl_seconds)
    except Exception:
        logger.debug("cache_rpush_json_items failed for key=%s", key, exc_info=True)


async def cache_lrange_json_items(key: str) -> list[dict[str, Any]]:
    """Read all JSON objects from a Redis list; falls back to legacy SET payloads."""
    try:
        client = get_redis_client()
        key_type = await client.type(key)
        if key_type in {"list", b"list"}:
            raw_items = await client.lrange(key, 0, -1)
            parsed: list[dict[str, Any]] = []
            for raw in raw_items:
                try:
                    item = json.loads(raw)
                    if isinstance(item, dict):
                        parsed.append(item)
                except json.JSONDecodeError:
                    continue
            return parsed
        return list((await cache_get(key) or {}).get("chunks") or [])
    except Exception:
        logger.debug("cache_lrange_json_items failed for key=%s", key, exc_info=True)
        return []
