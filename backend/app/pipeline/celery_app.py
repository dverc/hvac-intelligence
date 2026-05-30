from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "hvac_pipeline",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.pipeline.tasks.process_call_features": {"queue": "features"},
    },
    imports=("app.pipeline.tasks",),
)


from celery.signals import worker_ready


@worker_ready.connect
def _launch_kafka_consumer(**kwargs) -> None:
    """Start Kafka consumer thread when Celery worker boots (§6 Phase 4)."""
    import threading

    from app.pipeline.kafka_consumer import start_feature_consumer

    thread = threading.Thread(
        target=start_feature_consumer,
        name="kafka-feature-consumer",
        daemon=True,
    )
    thread.start()
