"""Business logic of the API service: persistence + enqueueing. No PDF work happens here."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.config import settings
from app.models import Job, JobStatus, Recipient, RecipientStatus
from app.schemas.recipient import fallback_recipient_fields, validate_recipient


class NoValidRecipientsError(Exception):
    def __init__(self, errors: list[dict[str, Any]]):
        super().__init__("no valid recipients in request")
        self.errors = errors


@dataclass
class CreatedJob:
    job_id: uuid.UUID
    recipient_id: uuid.UUID
    total: int
    valid: int
    invalid: int


def enqueue_certificate_task(job_id: str) -> None:
    """Publish the job to the Celery queue consumed by the dispatcher service."""
    celery_app.send_task(
        settings.CERTIFICATE_TASK_NAME,
        args=[job_id],
        queue=settings.CELERY_QUEUE,
    )


def parse_uuid(value: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def create_job(
    session: AsyncSession,
    title: str,
    raw_recipients: list[dict[str, Any]],
    user_id: uuid.UUID,
) -> CreatedJob:
    job_id = uuid.uuid4()
    rows: list[Recipient] = []
    errors: list[dict[str, Any]] = []
    valid = 0

    for index, raw in enumerate(raw_recipients):
        validated, error = validate_recipient(raw)
        if validated is not None:
            valid += 1
            rows.append(
                Recipient(
                    job_id=job_id,
                    name=validated.name,
                    email=str(validated.email),
                    course_name=validated.course_name,
                    completion_date=validated.completion_date,
                    status=RecipientStatus.PENDING.value,
                )
            )
        else:
            errors.append({"index": index, "error": error})
            rows.append(
                Recipient(
                    job_id=job_id,
                    status=RecipientStatus.FAILED.value,
                    error_message=error,
                    **fallback_recipient_fields(raw),
                )
            )

    if valid == 0:
        raise NoValidRecipientsError(errors)

    invalid = len(rows) - valid
    job = Job(
        id=job_id,
        user_id=user_id,
        title=title,
        status=JobStatus.PENDING.value,
        total_recipients=len(rows),
        processed_count=invalid,
        success_count=0,
        failed_count=invalid,
    )
    session.add(job)
    session.add_all(rows)
    await session.commit()
    return CreatedJob(job_id=job_id, recipient_id=rows[0].id, total=len(rows), valid=valid, invalid=invalid)


async def mark_job_failed(session: AsyncSession, job_id: uuid.UUID, message: str) -> None:
    pending = (
        await session.execute(
            select(func.count())
            .select_from(Recipient)
            .where(Recipient.job_id == job_id, Recipient.status == RecipientStatus.PENDING.value)
        )
    ).scalar_one()
    await session.execute(
        update(Recipient)
        .where(Recipient.job_id == job_id, Recipient.status == RecipientStatus.PENDING.value)
        .values(status=RecipientStatus.FAILED.value, error_message=message[:1000])
    )
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            status=JobStatus.FAILED.value,
            failed_count=Job.failed_count + pending,
            processed_count=Job.processed_count + pending,
        )
    )
    await session.commit()


async def get_job(session: AsyncSession, job_id: str, user_id: uuid.UUID) -> Optional[Job]:
    parsed = parse_uuid(job_id)
    if parsed is None:
        return None
    return await session.scalar(select(Job).where(Job.id == parsed, Job.user_id == user_id))


async def list_recipients(
    session: AsyncSession,
    job: Job,
    status: Optional[str],
    page: int,
    size: int,
) -> tuple[int, list[Recipient]]:
    conditions = [Recipient.job_id == job.id]
    if status:
        conditions.append(Recipient.status == status)
    total = (
        await session.execute(select(func.count()).select_from(Recipient).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(Recipient)
                .where(*conditions)
                .order_by(Recipient.created_at, Recipient.name, Recipient.id)
                .offset((page - 1) * size)
                .limit(size)
            )
        )
        .scalars()
        .all()
    )
    return total, list(rows)


async def get_recipient(session: AsyncSession, job: Job, recipient_id: str) -> Optional[Recipient]:
    parsed = parse_uuid(recipient_id)
    if parsed is None:
        return None
    recipient = await session.get(Recipient, parsed)
    if recipient is None or recipient.job_id != job.id:
        return None
    return recipient


async def list_successful_recipients(session: AsyncSession, job: Job) -> list[Recipient]:
    result = await session.execute(
        select(Recipient)
        .where(Recipient.job_id == job.id, Recipient.status == RecipientStatus.SUCCESS.value)
        .order_by(Recipient.name, Recipient.id)
    )
    return list(result.scalars().all())


def resolve_certificate_path(relative_path: Optional[str]) -> Optional[Path]:
    """Map a stored (storage-root relative) path to a file, refusing anything outside the root."""
    if not relative_path:
        return None
    root = Path(settings.STORAGE_PATH).resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate
