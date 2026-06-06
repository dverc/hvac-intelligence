import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.core.redis_lock import LockNotAcquiredError, RedisLock, build_slot_lock_key


@pytest.mark.asyncio
async def test_lock_is_acquired_successfully_when_key_does_not_exist():
    redis_client = AsyncMock()
    redis_client.set = AsyncMock(return_value=True)
    redis_client.delete = AsyncMock(return_value=1)

    async with RedisLock(redis_client, "lock:slot:test"):
        pass

    redis_client.set.assert_awaited_once_with(
        "lock:slot:test", "1", nx=True, ex=30
    )


@pytest.mark.asyncio
async def test_lock_not_acquired_error_when_key_already_exists():
    redis_client = AsyncMock()
    redis_client.set = AsyncMock(return_value=None)

    with pytest.raises(LockNotAcquiredError):
        async with RedisLock(redis_client, "lock:slot:taken"):
            pass

    redis_client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_lock_is_released_after_context_manager_exits_normally():
    redis_client = AsyncMock()
    redis_client.set = AsyncMock(return_value=True)
    redis_client.delete = AsyncMock(return_value=1)

    async with RedisLock(redis_client, "lock:slot:release"):
        pass

    redis_client.delete.assert_awaited_once_with("lock:slot:release")


@pytest.mark.asyncio
async def test_lock_is_released_after_context_manager_exits_with_exception():
    redis_client = AsyncMock()
    redis_client.set = AsyncMock(return_value=True)
    redis_client.delete = AsyncMock(return_value=1)

    with pytest.raises(RuntimeError):
        async with RedisLock(redis_client, "lock:slot:error"):
            raise RuntimeError("booking failed")

    redis_client.delete.assert_awaited_once_with("lock:slot:error")


def test_build_slot_lock_key_format():
    org_id = uuid.UUID("00000000-0000-4000-8000-000000000001")
    tech_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    key = build_slot_lock_key(org_id, tech_id, date(2026, 1, 12), "Monday Morning")
    assert key == (
        f"lock:slot:{org_id}:{tech_id}:2026-01-12:monday_morning"
    )
