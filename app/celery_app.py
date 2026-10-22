from celery import Celery

from app.config import REDIS_URL

celery_app = Celery(
    "axiomforge",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_publish_retry_policy={"max_retries": 1, "interval_start": 0, "interval_max": 0.2},
)
