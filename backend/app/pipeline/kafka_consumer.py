from __future__ import annotations

import json
import logging

from kafka import KafkaConsumer

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def start_feature_consumer() -> None:
    """
    Long-running Kafka consumer for 'call.features' topic.
    Deserializes CallFeatureVector payloads and dispatches Celery scoring tasks.
    Runs in a dedicated thread; launched by the Celery worker on startup.
    """
    settings = get_settings()
    consumer = KafkaConsumer(
        settings.KAFKA_TOPIC_CALL_FEATURES,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="churn-feature-pipeline",
        auto_offset_reset="earliest",
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        enable_auto_commit=False,
    )

    from app.pipeline.tasks import process_call_features

    logger.info("Feature pipeline Kafka consumer started on topic=%s", settings.KAFKA_TOPIC_CALL_FEATURES)
    for message in consumer:
        try:
            feature_payload = message.value
            process_call_features.delay(feature_payload)
            consumer.commit()
        except Exception as exc:
            logger.error("Consumer error: %s", exc, exc_info=True)
