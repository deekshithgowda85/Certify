import logging
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from celery.exceptions import CeleryError
from celery.exceptions import TimeoutError as CeleryTimeoutError
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.health import _fetch_pool_status
from app.config import settings
from app.database import get_session
from app.models import Job, JobStatus, Recipient, RecipientStatus

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


async def _get_queue_depth() -> int:
    client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    try:
        return int(await client.llen(settings.CELERY_QUEUE))
    finally:
        await client.aclose()


def _sandbox_slots(pool_status: dict, capacity: int) -> list[dict]:
    containers = pool_status.get("containers", [])[:capacity]
    busy_jobs = pool_status.get("busy_jobs", {})
    container_jobs = {container_id: job_id for job_id, container_id in busy_jobs.items()}
    slots = [
        {
            **container,
            "slot": index,
            "job_id": container_jobs.get(container.get("id")),
            "container_id": container.get("id"),
        }
        for index, container in enumerate(containers, start=1)
    ]
    slots.extend(
        {
            "id": f"slot-{index}",
            "slot": index,
            "name": f"Sandbox slot {index}",
            "role": "stopped",
            "status": "stopped",
            "health": "stopped",
            "job_id": None,
            "container_id": None,
            "cpu_percent": None,
            "mem_used_mb": None,
            "mem_limit_mb": None,
            "uptime_seconds": None,
            "job_progress": None,
        }
        for index in range(len(slots) + 1, capacity + 1)
    )
    return slots


async def _database_metrics(session: AsyncSession, now: datetime) -> dict:
    day_ago = now - timedelta(hours=24)
    recent_statuses = (
        await session.execute(
            select(Job.status, func.count(Job.id))
            .where(Job.updated_at >= day_ago)
            .group_by(Job.status)
        )
    ).all()
    status_counts = {status: count for status, count in recent_statuses}
    active_jobs = (
        await session.execute(
            select(Job.id, Job.processed_count, Job.total_recipients).where(
                Job.status == JobStatus.PROCESSING.value
            )
        )
    ).all()
    average_durations = (
        await session.execute(
            select(
                Job.processing_mode,
                func.avg(extract("epoch", Job.updated_at - Job.created_at)),
            )
            .where(
                Job.updated_at >= day_ago,
                Job.status.in_(
                    [
                        JobStatus.COMPLETED.value,
                        JobStatus.PARTIALLY_FAILED.value,
                        JobStatus.FAILED.value,
                    ]
                ),
                Job.processing_mode.is_not(None),
            )
            .group_by(Job.processing_mode)
        )
    ).all()

    minute_bucket = func.date_trunc("minute", Recipient.updated_at)
    throughput_rows = (
        await session.execute(
            select(minute_bucket, Job.processing_mode, func.count(Recipient.id))
            .join(Job, Job.id == Recipient.job_id)
            .where(
                Recipient.status == RecipientStatus.SUCCESS.value,
                Recipient.updated_at >= now.replace(second=0, microsecond=0) - timedelta(minutes=14),
            )
            .group_by(minute_bucket, Job.processing_mode)
            .order_by(minute_bucket)
        )
    ).all()

    start_minute = now.replace(second=0, microsecond=0) - timedelta(minutes=14)
    buckets = {
        start_minute + timedelta(minutes=index): {
            "minute": (start_minute + timedelta(minutes=index)).strftime("%H:%M"),
            "inline": 0,
            "sandbox": 0,
        }
        for index in range(15)
    }
    for minute, mode, count in throughput_rows:
        bucket = buckets.get(minute.replace(second=0, microsecond=0))
        if bucket is None:
            continue
        if mode == "INLINE":
            bucket["inline"] = count
        elif mode == "SANDBOX":
            bucket["sandbox"] = count

    failure_rows = (
        await session.execute(
            select(Recipient.error_message, func.count(Recipient.id))
            .where(
                Recipient.status == RecipientStatus.FAILED.value,
                Recipient.error_message.is_not(None),
                Recipient.updated_at >= day_ago,
            )
            .group_by(Recipient.error_message)
            .order_by(func.count(Recipient.id).desc())
            .limit(6)
        )
    ).all()

    recent_jobs = (
        await session.execute(
            select(Job)
            .where(Job.updated_at >= day_ago)
            .order_by(Job.updated_at.desc())
            .limit(40)
        )
    ).scalars().all()

    return {
        "processing": len(active_jobs),
        "active_jobs": {
            str(job_id): {"processed": processed, "total": total}
            for job_id, processed, total in active_jobs
        },
        "avg_seconds": {
            mode.lower(): float(seconds)
            for mode, seconds in average_durations
            if mode and seconds is not None
        },
        "completed_24h": status_counts.get(JobStatus.COMPLETED.value, 0),
        "failed_24h": status_counts.get(JobStatus.FAILED.value, 0)
        + status_counts.get(JobStatus.PARTIALLY_FAILED.value, 0),
        "throughput": list(buckets.values()),
        "failures": [{"message": message, "count": count} for message, count in failure_rows],
        "events": [
            {
                "ts": job.updated_at.isoformat(),
                "level": (
                    "error"
                    if job.status == JobStatus.FAILED.value
                    else "warn"
                    if job.status == JobStatus.PARTIALLY_FAILED.value
                    else "info"
                ),
                "text": f"Job {str(job.id)[:8]} · {job.title} — {job.status.replace('_', ' ').lower()}",
            }
            for job in recent_jobs
        ],
    }


@router.get("/metrics")
async def metrics(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Return queue, dispatcher, and five-slot sandbox health metrics."""
    now = datetime.now(timezone.utc)
    queue_depth = -1
    try:
        queue_depth = await _get_queue_depth()
    except (aioredis.RedisError, OSError) as exc:
        logger.warning("Could not read certificate queue depth: %s", exc)

    dispatcher_status = "healthy"
    try:
        pool_status = await run_in_threadpool(_fetch_pool_status)
        if pool_status.get("status") in {"degraded", "starting"}:
            dispatcher_status = pool_status["status"]
    except (CeleryError, CeleryTimeoutError, OSError) as exc:
        logger.warning("Dispatcher metrics unavailable: %s", exc)
        dispatcher_status = "unavailable"
        pool_status = {
            "containers": [],
            "idle": 0,
            "busy": 0,
            "max_total": settings.SANDBOX_MAX_CONTAINERS,
        }

    database_stats = await _database_metrics(session, now)
    queue_status = (
        "unknown"
        if queue_depth < 0
        else "backlogged"
        if queue_depth > 10
        else "busy"
        if queue_depth > 0
        else "ok"
    )
    busy_jobs = pool_status.get("busy_jobs", {})
    container_jobs = {container_id: job_id for job_id, container_id in busy_jobs.items()}
    active_jobs = database_stats["active_jobs"]
    containers = []
    for container in pool_status.get("containers", []):
        job_id = container_jobs.get(container.get("id"))
        containers.append(
            {
                **container,
                "job_id": job_id,
                "job_progress": active_jobs.get(str(job_id)) if job_id else None,
            }
        )
    capacity = max(1, int(pool_status.get("max_total", settings.SANDBOX_MAX_CONTAINERS)))
    slots = _sandbox_slots(pool_status, capacity)
    for slot in slots:
        job_id = slot.get("job_id") or container_jobs.get(slot.get("id"))
        slot["job_id"] = job_id
        slot["job_progress"] = active_jobs.get(str(job_id)) if job_id else None
    body = {
        "status": "ok" if queue_depth >= 0 and dispatcher_status == "healthy" else "degraded",
        "updated_at": now.isoformat(),
        "queue": {
            "name": settings.CELERY_QUEUE,
            "pending": queue_depth,
            "processing": database_stats["processing"],
            "completed_24h": database_stats["completed_24h"],
            "failed_24h": database_stats["failed_24h"],
            "status": queue_status,
        },
        "services": {
            "api": "ok",
            "db": "ok",
            "redis": "ok" if queue_depth >= 0 else "error",
            "dispatcher": (
                "ok" if dispatcher_status == "healthy"
                else "down" if dispatcher_status == "unavailable"
                else "degraded"
            ),
        },
        "dispatcher": {"status": dispatcher_status},
        "containers": containers,
        "sandboxes": {
            "capacity": capacity,
            "active": pool_status.get("busy", 0),
            "idle": pool_status.get("idle", 0),
            "slots": slots,
        },
        "pool": {
            "idle": pool_status.get("idle", 0),
            "busy": pool_status.get("busy", 0),
            "min_idle": pool_status.get("min_idle", 0),
            "max_total": capacity,
            "status": pool_status.get("status", dispatcher_status),
            "boot_errors": pool_status.get("boot_errors", 0),
            "waiting_jobs": max(0, queue_depth) if queue_depth >= 0 else None,
        },
        "throughput": database_stats["throughput"],
        "avg_seconds": database_stats["avg_seconds"],
        "failures": database_stats["failures"],
        "events": database_stats["events"],
    }
    return JSONResponse(body)