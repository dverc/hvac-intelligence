import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.cache import (
    cache_delete,
    cache_get,
    cache_set,
    customer_cache_key,
    org_cache_key,
)


@pytest.mark.asyncio
async def test_cache_get_returns_none_on_cache_miss():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    with patch("app.core.cache.get_redis_client", return_value=mock_redis):
        assert await cache_get("missing:key") is None


@pytest.mark.asyncio
async def test_cache_set_and_cache_get_round_trip():
    store: dict[str, str] = {}

    mock_redis = AsyncMock()

    async def _set(key: str, value: str, ex: int | None = None) -> bool:
        store[key] = value
        return True

    mock_redis.set.side_effect = _set
    mock_redis.get.side_effect = lambda key: store.get(key)

    payload = {"found": True, "customer_id": "abc-123"}
    with patch("app.core.cache.get_redis_client", return_value=mock_redis):
        await cache_set("customer:org:phone", payload, 300)
        result = await cache_get("customer:org:phone")

    assert result == payload
    mock_redis.set.assert_awaited_once_with(
        "customer:org:phone", json.dumps(payload), ex=300
    )


@pytest.mark.asyncio
async def test_cache_delete_removes_key():
    store = {"org:1:settings": json.dumps({"timezone": "UTC"})}

    mock_redis = AsyncMock()

    async def _delete(key: str) -> int:
        return 1 if store.pop(key, None) is not None else 0

    mock_redis.delete.side_effect = _delete
    mock_redis.get.side_effect = lambda key: store.get(key)

    with patch("app.core.cache.get_redis_client", return_value=mock_redis):
        await cache_delete("org:1:settings")
        assert await cache_get("org:1:settings") is None


@pytest.mark.asyncio
async def test_cache_get_returns_none_when_redis_unavailable():
    with patch(
        "app.core.cache.get_redis_client",
        side_effect=RuntimeError("redis unavailable"),
    ):
        assert await cache_get("any:key") is None


def test_customer_cache_key_format():
    assert customer_cache_key("org-1", "+15551234567") == "customer:org-1:+15551234567"


def test_org_cache_key_format():
    assert org_cache_key("org-1") == "org:org-1:settings"
