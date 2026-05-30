"""Kafka producer for call.features — no imports from services/ or tasks/."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def publish_call_features(payload: dict[str, Any]) -> bool:
    """
    Publish a CallFeatureVector trigger payload to the call.features topic.
    Returns False when Kafka is unavailable (logged; pipeline can still run via direct Celery in dev).
    """
    settings = get_settings()
    try:
        from kafka import KafkaProducer

        producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            acks="all",
            retries=3,
        )
        producer.send(settings.KAFKA_TOPIC_CALL_FEATURES, payload)
        producer.flush(timeout=10)
        producer.close()
        logger.info(
            "Published call.features for customer_id=%s call_id=%s",
            payload.get("customer_id"),
            payload.get("call_id"),
        )
        return True
    except Exception as exc:
        logger.warning("Kafka publish failed: %s", exc)
        return False
