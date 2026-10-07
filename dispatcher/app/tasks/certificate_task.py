"""The dispatcher's brain: choose INLINE vs SANDBOX for a job and run it."""
from __future__ import annotations

import logging
from typing import Optional

from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.config import settings
from app.services import job_repository as repo
from app.services.inline_generator import run_inline
from app.services.sandbox_runner import run_sandbox

logger = logging.getLogger(__name__)

TASK_NAME = "app.tasks.certificate_task.certificate_task"
INLINE = "INLINE"
SANDBOX = "SANDBOX"
NOTHING_TO_DO = "NOTHING_TO_DO"


def decide_mode(pending_count: int, threshold: Optional[int] = None) -> str:
    """<= threshold -> INLINE, otherwise SANDBOX."""
    limit = settings.SANDBOX_THRESHOLD if threshold is None else threshold
    return INLINE if pending_count <= limit else SANDBOX


def process_job(job_id: str) -> str:
    """Run one job. Returns the mode used, or NOTHING_TO_DO."""
    pending = repo.count_pending_recipients(job_id)
    if pending == 0:
        repo.finalize_job(job_id)
        return NOTHING_TO_DO

    mode = decide_mode(pending)
    repo.update_job_mode(job_id, mode)
    logger.info("Job %s: %s pending recipient(s) -> %s mode", job_id, pending, mode)

    if mode == INLINE:
        run_inline(job_id)
    else:
        run_sandbox(job_id)  # uses the container pool internally; blocks if the pool is full

    repo.finalize_job(job_id)
    return mode


def _fail_job(job_id: str, message: str) -> None:
    try:
        repo.mark_all_recipients_failed(job_id, message)
        repo.finalize_job(job_id)
    except Exception:
        logger.exception("Could not mark job %s as failed", job_id)


@celery_app.task(
    bind=True,
    name=TASK_NAME,
    max_retries=3,
    soft_time_limit=settings.TASK_SOFT_TIME_LIMIT,  # 600s  > container timeout (300s)
    time_limit=settings.TASK_TIME_LIMIT,
)
def certificate_task(self, job_id: str) -> dict:
    try:
        outcome = process_job(job_id)
    except SoftTimeLimitExceeded:
        _fail_job(job_id, "Task exceeded its time limit")
        raise
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            logger.exception("Job %s failed permanently", job_id)
            _fail_job(job_id, f"Processing failed after retries: {exc}")
            raise
        countdown = min(60, 5 * 2 ** self.request.retries)
        logger.warning("Job %s failed (%s); retry in %ss", job_id, exc, countdown)
        raise self.retry(exc=exc, countdown=countdown)

    return {"job_id": job_id, "outcome": outcome}


@celery_app.task(name="app.tasks.certificate_task.pool_status")
def pool_status() -> dict:
    """Used by GET /api/v1/pool/status (the API has no Docker access)."""
    from app.pool.container_pool import pool

    return pool.status()
