"""Redis distributed locks for concurrent booking protection."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any


class LockNotAcquiredError(Exception):
    """Raised when a Redis lock key is already held by another caller."""


def build_slot_lock_key(
    org_id: uuid.UUID,
    technician_id: uuid.UUID,
    slot_date: date | str,
    preferred_window: str,
) -> str:
    """Build the Redis key for a technician slot booking lock."""
    date_value = slot_date.isoformat() if isinstance(slot_date, date) else slot_date
    window = preferred_window.strip().lower().replace(" ", "_")
    return f"lock:slot:{org_id}:{technician_id}:{date_value}:{window}"


class RedisLock:
    """Async context manager that acquires a Redis lock with SET NX EX."""

    def __init__(
        self,
        redis_client: Any,
        key: str,
        timeout_seconds: int = 30,
    ) -> None:
        self.redis_client = redis_client
        self.key = key
        self.timeout_seconds = timeout_seconds
        self._acquired = False

    async def __aenter__(self) -> RedisLock:
        acquired = await self.redis_client.set(
            self.key,
            "1",
            nx=True,
            ex=self.timeout_seconds,
        )
        if not acquired:
            raise LockNotAcquiredError(self.key)
        self._acquired = True
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self._acquired:
            await self.redis_client.delete(self.key)
            self._acquired = False
        return False
