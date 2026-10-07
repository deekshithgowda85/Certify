"""Celery client used by the API only to *enqueue* work for the dispatcher service."""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "certificate_api",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_default_queue=settings.CELERY_QUEUE,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
)
