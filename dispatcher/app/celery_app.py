"""Celery application of the dispatcher (the worker that decides INLINE vs SANDBOX)."""
from celery import Celery
from celery.signals import worker_process_init, worker_ready, worker_shutdown

from app.config import settings

celery_app = Celery(
    "certificate_dispatcher",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.certificate_task"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_default_queue=settings.CELERY_QUEUE,
    task_routes={"app.tasks.certificate_task.certificate_task": {"queue": settings.CELERY_QUEUE}},
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_track_started=True,
    # Long-running tasks: only fetch one at a time and ack after completion.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
)

# aliases so `celery -A app.celery_app` always finds the application
app = celery_app
celery = celery_app


@worker_process_init.connect
def _reset_db_pool(**_kwargs) -> None:
    """Never share DB connections across forked worker processes."""
    from app.database import engine

    engine.dispose()


@worker_shutdown.connect
def shutdown_pool(sender=None, **kwargs):
    from app.pool.container_pool import pool

    pool.shutdown()


@worker_ready.connect
def start_pool(sender=None, **kwargs):
    from app.pool.container_pool import pool

    pool.start()
