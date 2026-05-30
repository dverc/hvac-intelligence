"""
Redis pub/sub wrapper for dashboard SSE (§5.1.5).

Channels:
  - call.active        → CALL_ACTIVE
  - churn.intervention → INTERVENTION_COMPLETE
  - batch.complete     → BATCH_SCORE_COMPLETE
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CHANNEL_CALL_ACTIVE = "call.active"
CHANNEL_INTERVENTION = "churn.intervention"
CHANNEL_BATCH_COMPLETE = "batch.complete"

ALL_SSE_CHANNELS = (
    CHANNEL_CALL_ACTIVE,
    CHANNEL_INTERVENTION,
    CHANNEL_BATCH_COMPLETE,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def publish_event_sync(channel: str, event: dict[str, Any]) -> None:
    """Publish from Celery / sync contexts."""
    settings = get_settings()
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.publish(channel, json.dumps(event))
        client.close()
    except Exception as exc:
        logger.warning("Redis publish failed on channel %s: %s", channel, exc)


async def publish_event(channel: str, event: dict[str, Any]) -> None:
    """Publish from async FastAPI handlers."""
    settings = get_settings()
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.publish(channel, json.dumps(event))
        await client.aclose()
    except Exception as exc:
        logger.warning("Redis publish failed on channel %s: %s", channel, exc)


async def publish_call_active_event(
    *,
    call_id: str,
    customer_id: str,
    customer_name: str,
    churn_risk_tier: str,
    churn_probability: float,
    call_duration_seconds: int = 0,
    current_sentiment: float | None = None,
    dominant_intent: str = "UNKNOWN",
    intervention_triggered: bool = True,
) -> None:
    event = {
        "event_type": "CALL_ACTIVE",
        "call_id": call_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "churn_risk_tier": churn_risk_tier,
        "churn_probability": churn_probability,
        "call_duration_seconds": call_duration_seconds,
        "current_sentiment": current_sentiment if current_sentiment is not None else 0.0,
        "dominant_intent": dominant_intent,
        "intervention_triggered": intervention_triggered,
        "timestamp": _utc_now_iso(),
    }
    await publish_event(CHANNEL_CALL_ACTIVE, event)


def publish_intervention_complete_sync(event: dict[str, Any]) -> None:
    payload = {**event, "event_type": "INTERVENTION_COMPLETE"}
    if "timestamp" not in payload:
        payload["timestamp"] = _utc_now_iso()
    publish_event_sync(CHANNEL_INTERVENTION, payload)


def publish_batch_score_complete_sync(
    *,
    accounts_scored: int,
    new_critical: int,
    resolved_critical: int,
) -> None:
    event = {
        "event_type": "BATCH_SCORE_COMPLETE",
        "accounts_scored": accounts_scored,
        "new_critical": new_critical,
        "resolved_critical": resolved_critical,
        "timestamp": _utc_now_iso(),
    }
    publish_event_sync(CHANNEL_BATCH_COMPLETE, event)


class EventBus:
    """Async Redis pub/sub consumer for SSE streaming."""

    def __init__(self) -> None:
        self._redis: Any | None = None

    async def __aenter__(self) -> EventBus:
        from redis.asyncio import Redis

        settings = get_settings()
        self._redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def subscribe(self, channels: list[str]) -> AsyncIterator[dict[str, Any]]:
        if self._redis is None:
            raise RuntimeError("EventBus not initialized; use async with EventBus()")

        pubsub = self._redis.pubsub()
        await pubsub.subscribe(*channels)
        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if not data:
                    continue
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON on Redis channel: %s", data)
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.close()
