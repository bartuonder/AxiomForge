import os

from celery import Celery

from app.config import REDIS_URL

DEFAULT_VISIBILITY_TIMEOUT_SECONDS = 7200


def visibility_timeout() -> int:
    try:
        value = int(os.getenv("CELERY_VISIBILITY_TIMEOUT", ""))
    except ValueError:
        return DEFAULT_VISIBILITY_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_VISIBILITY_TIMEOUT_SECONDS

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
    broker_transport_options={"visibility_timeout": visibility_timeout()},
    task_publish_retry_policy={"max_retries": 1, "interval_start": 0, "interval_max": 0.2},
)
