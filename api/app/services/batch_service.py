from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Job, JobBatch, JobStatus, Recipient, RecipientStatus
from app.services import job_service


@dataclass
class BatchRegeneration:
    jobs: list[Job]
    recipients_to_regenerate: int


class BatchIdempotencyConflictError(Exception):
    pass


@dataclass
class CreatedBatch:
    batch_id: uuid.UUID
    jobs: list[job_service.CreatedJob]
    replayed: bool = False

    @property
    def total(self) -> int:
        return sum(job.total for job in self.jobs)

    @property
    def valid(self) -> int:
        return sum(job.valid for job in self.jobs)

    @property
    def invalid(self) -> int:
        return sum(job.invalid for job in self.jobs)


def _fingerprint(title: str, recipients: list[Any]) -> str:
    return job_service.request_fingerprint(title, recipients)


async def _find_replay(
    session: AsyncSession,
    user_id: Optional[uuid.UUID],
    idempotency_key: str,
    fingerprint: str,
) -> Optional[CreatedBatch]:
    batch = await session.scalar(
        select(JobBatch).where(
            JobBatch.user_id == user_id,
            JobBatch.idempotency_key == idempotency_key,
        )
    )
    if batch is None:
        return None
    if batch.request_fingerprint != fingerprint:
        raise BatchIdempotencyConflictError(
            "Idempotency-Key was already used with a different request"
        )
    jobs = (
        await session.execute(
            select(Job).where(Job.batch_id == batch.id).order_by(Job.created_at, Job.id)
        )
    ).scalars().all()
    return CreatedBatch(
        batch_id=batch.id,
        jobs=[
            job_service.CreatedJob(
                job_id=job.id,
                total=job.total_recipients,
                valid=job.valid_recipients,
                invalid=job.invalid_recipients,
                replayed=True,
                enqueue_error=job.enqueue_error,
            )
            for job in jobs
        ],
        replayed=True,
    )


async def create_batch(
    session: AsyncSession,
    title: str,
    raw_recipients: list[Any],
    user_id: Optional[uuid.UUID],
    idempotency_key: Optional[str] = None,
) -> CreatedBatch:
    fingerprint = _fingerprint(title, raw_recipients)
    if idempotency_key:
        replay = await _find_replay(session, user_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay

    batch = JobBatch(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint if idempotency_key else None,
    )
    session.add(batch)
    jobs: list[job_service.CreatedJob] = []
    recipients_per_job = settings.MAX_RECIPIENTS_PER_JOB
    try:
        await session.flush()
        for start in range(0, len(raw_recipients), recipients_per_job):
            chunk = raw_recipients[start : start + recipients_per_job]
            created = await job_service.create_job(
                session,
                title,
                chunk,
                user_id,
                batch_id=batch.id,
                allow_all_invalid=True,
                commit=False,
                recipient_offset=start,
            )
            jobs.append(created)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if idempotency_key:
            replay = await _find_replay(session, user_id, idempotency_key, fingerprint)
            if replay is not None:
                return replay
        raise
    except Exception:
        await session.rollback()
        raise
    return CreatedBatch(batch_id=batch.id, jobs=jobs)


async def get_batch(
    session: AsyncSession, batch_id: str, user_id: Optional[uuid.UUID], public: bool
) -> Optional[JobBatch]:
    parsed = job_service.parse_uuid(batch_id)
    if parsed is None:
        return None
    statement = select(JobBatch).where(JobBatch.id == parsed)
    if public:
        statement = statement.where(JobBatch.user_id.is_(None))
    else:
        statement = statement.where(JobBatch.user_id == user_id)
    return await session.scalar(statement)


async def batch_jobs(session: AsyncSession, batch: JobBatch) -> list[Job]:
    return list(
        (
            await session.execute(
                select(Job).where(Job.batch_id == batch.id).order_by(Job.created_at, Job.id)
            )
        ).scalars().all()
    )


def batch_status(jobs: list[Job]) -> str:
    if not jobs:
        return JobStatus.PENDING.value
    terminal = {
        JobStatus.COMPLETED.value,
        JobStatus.PARTIALLY_FAILED.value,
        JobStatus.FAILED.value,
    }
    if any(job.status not in terminal for job in jobs):
        return (
            JobStatus.PROCESSING.value
            if any(job.status == JobStatus.PROCESSING.value for job in jobs)
            else JobStatus.PENDING.value
        )
    successful = sum(job.success_count for job in jobs)
    failed = sum(job.failed_count for job in jobs)
    if successful == 0:
        return JobStatus.FAILED.value
    if failed:
        return JobStatus.PARTIALLY_FAILED.value
    return JobStatus.COMPLETED.value


def batch_response(batch: JobBatch, jobs: list[Job]) -> dict[str, Any]:
    return {
        "job_id": batch.id,
        "title": batch.title,
        "status": batch_status(jobs),
        "total_recipients": sum(job.total_recipients for job in jobs),
        "processed_count": sum(job.processed_count for job in jobs),
        "success_count": sum(job.success_count for job in jobs),
        "failed_count": sum(job.failed_count for job in jobs),
        "created_at": batch.created_at,
        "updated_at": max((job.updated_at for job in jobs), default=batch.updated_at),
    }


async def list_failed_recipients(
    session: AsyncSession, batch: JobBatch, page: int, size: int, status: Optional[str] = None
) -> tuple[int, list[Recipient]]:
    base = select(Recipient).join(Job, Recipient.job_id == Job.id).where(Job.batch_id == batch.id)
    if status is not None:
        base = base.where(Recipient.status == status)
    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    )
    rows = (
        await session.execute(
            base.order_by(Recipient.source_index.asc().nulls_last(), Recipient.id)
            .offset((page - 1) * size)
            .limit(size)
        )
    ).scalars().all()
    return int(total or 0), list(rows)


async def list_successful_recipients(session: AsyncSession, batch: JobBatch) -> list[Recipient]:
    return list(
        (
            await session.execute(
                select(Recipient)
                .join(Job, Recipient.job_id == Job.id)
                .where(
                    Job.batch_id == batch.id,
                    Recipient.status == RecipientStatus.SUCCESS.value,
                )
                .order_by(Recipient.source_index.asc().nulls_last(), Recipient.id)
            )
        ).scalars().all()
    )


async def prepare_batch_regeneration(
    session: AsyncSession, batch: JobBatch
) -> BatchRegeneration:
    locked_batch = await session.scalar(
        select(JobBatch).where(JobBatch.id == batch.id).with_for_update()
    )
    if locked_batch is None:
        raise LookupError("Batch not found")

    jobs = list(
        (
            await session.execute(
                select(Job)
                .where(Job.batch_id == locked_batch.id)
                .order_by(Job.created_at, Job.id)
                .with_for_update()
            )
        ).scalars().all()
    )
    terminal_statuses = {
        JobStatus.COMPLETED.value,
        JobStatus.PARTIALLY_FAILED.value,
        JobStatus.FAILED.value,
    }
    if any(job.status not in terminal_statuses for job in jobs):
        raise ValueError("Wait for the batch to finish before regenerating certificates")

    successful = await list_successful_recipients(session, locked_batch)
    if not successful:
        raise ValueError("This batch has no successful recipients to regenerate")
    if all(
        (path := job_service.resolve_certificate_path(recipient.certificate_path)) is not None
        and path.is_file()
        for recipient in successful
    ):
        raise FileExistsError("The batch certificates are still available to download")

    for recipient in successful:
        recipient.status = RecipientStatus.PENDING.value
        recipient.certificate_path = None
        recipient.error_message = None

    jobs_to_enqueue = []
    for job in jobs:
        if not any(recipient.job_id == job.id for recipient in successful):
            continue
        job.status = JobStatus.PENDING.value
        job.success_count = 0
        job.processed_count = job.failed_count
        job.processing_mode = None
        job.container_id = None
        job.enqueue_error = None
        jobs_to_enqueue.append(job)

    await session.commit()
    return BatchRegeneration(jobs=jobs_to_enqueue, recipients_to_regenerate=len(successful))
