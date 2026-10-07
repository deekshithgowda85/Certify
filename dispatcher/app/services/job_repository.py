"""All database access of the dispatcher (synchronous SQLAlchemy)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update

from app.database import session_scope
from app.models import Job, Recipient

MAX_ERROR_LENGTH = 1000


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def count_pending_recipients(job_id: str) -> int:
    with session_scope() as session:
        return session.execute(
            select(func.count()).select_from(Recipient).where(
                Recipient.job_id == _uuid(job_id), Recipient.status == "PENDING"
            )
        ).scalar_one()


def fetch_pending_recipients(job_id: str) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(Recipient)
            .where(Recipient.job_id == _uuid(job_id), Recipient.status == "PENDING")
            .order_by(Recipient.created_at, Recipient.name, Recipient.id)
        ).scalars().all()
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "email": r.email,
                "course_name": r.course_name,
                "completion_date": r.completion_date.isoformat(),
            }
            for r in rows
        ]


def update_job_mode(job_id: str, mode: str) -> None:
    with session_scope() as session:
        session.execute(
            update(Job).where(Job.id == _uuid(job_id)).values(status="PROCESSING", processing_mode=mode)
        )


def update_job_status(job_id: str, status: str) -> None:
    with session_scope() as session:
        session.execute(update(Job).where(Job.id == _uuid(job_id)).values(status=status))


def update_job_container_id(job_id: str, container_id: str) -> None:
    with session_scope() as session:
        session.execute(
            update(Job).where(Job.id == _uuid(job_id)).values(container_id=container_id[:64])
        )


def record_success(job_id: str, recipient_id: str, certificate_path: str) -> None:
    """One transaction per recipient: mark SUCCESS and bump the job counters."""
    with session_scope() as session:
        result = session.execute(
            update(Recipient)
            .where(Recipient.id == _uuid(recipient_id), Recipient.status == "PENDING")
            .values(status="SUCCESS", certificate_path=certificate_path, error_message=None)
        )
        if result.rowcount:
            session.execute(
                update(Job)
                .where(Job.id == _uuid(job_id))
                .values(
                    success_count=Job.success_count + 1,
                    processed_count=Job.processed_count + 1,
                )
            )


def record_failure(job_id: str, recipient_id: str, error: str) -> None:
    with session_scope() as session:
        result = session.execute(
            update(Recipient)
            .where(Recipient.id == _uuid(recipient_id), Recipient.status == "PENDING")
            .values(status="FAILED", error_message=error[:MAX_ERROR_LENGTH])
        )
        if result.rowcount:
            session.execute(
                update(Job)
                .where(Job.id == _uuid(job_id))
                .values(
                    failed_count=Job.failed_count + 1,
                    processed_count=Job.processed_count + 1,
                )
            )


def mark_all_recipients_failed(job_id: str, error: str) -> int:
    """Mark every recipient that is still PENDING as FAILED. Returns how many were changed."""
    with session_scope() as session:
        result = session.execute(
            update(Recipient)
            .where(Recipient.job_id == _uuid(job_id), Recipient.status == "PENDING")
            .values(status="FAILED", error_message=error[:MAX_ERROR_LENGTH])
        )
        changed = result.rowcount or 0
        if changed:
            session.execute(
                update(Job)
                .where(Job.id == _uuid(job_id))
                .values(
                    failed_count=Job.failed_count + changed,
                    processed_count=Job.processed_count + changed,
                )
            )
        return changed


def finalize_job(job_id: str) -> str:
    """Recompute counters from the recipients table (source of truth) and set the final status.

    The status is left untouched while recipients are still PENDING.
    """
    with session_scope() as session:
        counts = dict(
            session.execute(
                select(Recipient.status, func.count())
                .where(Recipient.job_id == _uuid(job_id))
                .group_by(Recipient.status)
            ).all()
        )
        success = counts.get("SUCCESS", 0)
        failed = counts.get("FAILED", 0)
        pending = counts.get("PENDING", 0)

        job = session.get(Job, _uuid(job_id))
        if job is None:
            raise LookupError(f"job {job_id} not found")
        job.success_count = success
        job.failed_count = failed
        job.processed_count = success + failed
        if pending == 0:
            if success == 0:
                job.status = "FAILED"
            elif failed == 0:
                job.status = "COMPLETED"
            else:
                job.status = "PARTIALLY_FAILED"
        return job.status
