from __future__ import annotations

import logging

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

logger = logging.getLogger(__name__)

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
    imports=("app.pipeline.tasks", "app.tasks.celery_tasks"),
    beat_schedule={
        "sync-technician-schedules": {
            "task": "app.pipeline.tasks.sync_technician_schedules",
            "schedule": crontab(minute=0, hour="*/2"),
        },
        "batch-rescore-customers": {
            "task": "app.pipeline.tasks.batch_rescore_customers",
            "schedule": crontab(minute=0, hour=2),
        },
        "sync-google-calendars": {
            "task": "app.pipeline.tasks.sync_google_calendars",
            "schedule": crontab(minute=0, hour="*/4"),
        },
        "sync-jobber-data": {
            "task": "app.pipeline.tasks.sync_jobber_data",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "sync-google-drive": {
            "task": "app.pipeline.tasks.sync_google_drive_folders",
            "schedule": crontab(minute="*/30"),
        },
        "send-weekly-client-reports": {
            "task": "app.pipeline.tasks.send_weekly_client_reports",
            "schedule": crontab(hour=8, minute=0, day_of_week=1),
        },
        "check-model-drift-and-retrain": {
            "task": "app.pipeline.tasks.check_model_drift_and_retrain",
            "schedule": crontab(minute=0, hour=3),
        },
        "check-and-launch-outbound-campaigns": {
            "task": "app.tasks.celery_tasks.check_and_launch_campaigns",
            "schedule": crontab(minute=0, hour=10),
        },
    },
)


from celery.signals import worker_ready


@worker_ready.connect
def _launch_kafka_consumer(**kwargs) -> None:
    """Start Kafka consumer thread when Celery worker boots (§6 Phase 4)."""
    import threading

    try:
        from app.pipeline.kafka_consumer import start_feature_consumer
    except ImportError as exc:
        logger.warning(
            "Kafka consumer not started — kafka-python unavailable (%s). "
            "Celery direct task dispatch still works.",
            exc,
        )
        return

    thread = threading.Thread(
        target=start_feature_consumer,
        name="kafka-feature-consumer",
        daemon=True,
    )
    thread.start()
    logger.info("Kafka feature consumer thread launched")
