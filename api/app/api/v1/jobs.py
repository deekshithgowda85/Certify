import os
import re
import tempfile
import zipfile
import uuid
from pathlib import Path
from typing import Annotated, Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from starlette.background import BackgroundTask

from app.database import get_session
from app.auth import get_current_user
from app.models import Job, Recipient, RecipientStatus, User
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobListResponse, JobResponse
from app.schemas.recipient import RecipientListResponse, RecipientOut
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])
CurrentUser = Annotated[User, Depends(get_current_user)]

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t\x00]+')


def safe_filename(value: str, fallback: str = "certificate") -> str:
    cleaned = _UNSAFE_FILENAME.sub("_", value).strip(" ._")
    return cleaned or fallback


def content_disposition(filename: str) -> str:
    """attachment header with an ASCII fallback plus the RFC 5987 UTF-8 form for non-ASCII names."""
    fallback = filename.encode("ascii", "ignore").decode().replace('"', "") or "download"
    return f"attachment; filename=\"{fallback}\"; filename*=utf-8\'\'{quote(filename)}"


async def _job_or_404(session: AsyncSession, job_id: str, current_user: User) -> Job:
    parsed_job_id = job_service.parse_uuid(job_id)
    if parsed_job_id is None:
        raise HTTPException(status_code=404, detail="Job not found")
    unowned_job = await session.get(Job, parsed_job_id)
    if unowned_job is not None and unowned_job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this job")
    job = await job_service.get_job(session, job_id, current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _job_response(job: Job, recipient_id: Optional[uuid.UUID] = None) -> JobResponse:
    return JobResponse(
        job_id=job.id,
        title=job.title,
        status=job.status,
        processing_mode=job.processing_mode,
        total_recipients=job.total_recipients,
        processed_count=job.processed_count,
        success_count=job.success_count,
        failed_count=job.failed_count,
        container_id=job.container_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        recipient_id=recipient_id,
    )


@router.post("", response_model=JobCreateResponse, status_code=202)
async def create_job(
    payload: JobCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    try:
        created = await job_service.create_job(session, payload.title, payload.recipients, current_user.id)
    except job_service.NoValidRecipientsError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No valid recipients in request",
                "errors": exc.errors[:50],
            },
        )

    try:
        await run_in_threadpool(job_service.enqueue_certificate_task, str(created.job_id))
    except Exception as exc:  # broker unreachable etc.
        await job_service.mark_job_failed(session, created.job_id, f"Could not enqueue job: {exc}")
        raise HTTPException(status_code=503, detail="Could not enqueue job; please retry later")

    return JobCreateResponse(
        job_id=created.job_id,
        recipient_id=created.recipient_id,
        status="PENDING",
        total_recipients=created.total,
        valid_recipients=created.valid,
        invalid_recipients=created.invalid,
        processing_mode=None,
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(current_user: CurrentUser, session: AsyncSession = Depends(get_session)) -> JobListResponse:
    jobs = list(
        (
            await session.execute(
                select(Job).where(Job.user_id == current_user.id).order_by(Job.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    if not jobs:
        return JobListResponse(jobs=[])
    recipient_rows = (
        await session.execute(
            select(Recipient.job_id, Recipient.id)
            .where(Recipient.job_id.in_([job.id for job in jobs]))
            .order_by(Recipient.created_at, Recipient.id)
        )
    ).all()
    recipient_ids = {job_id: recipient_id for job_id, recipient_id in reversed(recipient_rows)}
    return JobListResponse(jobs=[_job_response(job, recipient_ids.get(job.id)) for job in jobs])


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, current_user: CurrentUser, session: AsyncSession = Depends(get_session)):
    job = await _job_or_404(session, job_id, current_user)
    return _job_response(job)


@router.get("/{job_id}/recipients", response_model=RecipientListResponse)
async def list_recipients(
    job_id: str,
    current_user: CurrentUser,
    status: Optional[Literal["PENDING", "SUCCESS", "FAILED"]] = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    job = await _job_or_404(session, job_id, current_user)
    total, rows = await job_service.list_recipients(session, job, status, page, size)
    items = [
        RecipientOut(
            id=r.id,
            name=r.name,
            email=r.email,
            status=r.status,
            error_message=r.error_message,
            certificate_url=(
                f"/api/v1/jobs/{job.id}/certificates/{r.id}"
                if r.status == RecipientStatus.SUCCESS.value
                else None
            ),
        )
        for r in rows
    ]
    return RecipientListResponse(job_id=job.id, total=total, page=page, size=size, recipients=items)


# NOTE: must be declared before the "{recipient_id}" route so "download-all" is not captured by it.
@router.get("/{job_id}/certificates/download-all")
async def download_all(job_id: str, current_user: CurrentUser, session: AsyncSession = Depends(get_session)):
    job = await _job_or_404(session, job_id, current_user)
    recipients = await job_service.list_successful_recipients(session, job)

    entries: list[tuple[Path, str]] = []
    for recipient in recipients:
        path = job_service.resolve_certificate_path(recipient.certificate_path)
        if path is not None:
            arcname = f"{safe_filename(recipient.name)}_{str(recipient.id)[:8]}.pdf"
            entries.append((path, arcname))
    if not entries:
        raise HTTPException(status_code=404, detail="No certificates available for this job")

    handle = tempfile.NamedTemporaryFile(prefix="certificates_", suffix=".zip", delete=False)
    handle.close()
    try:
        await run_in_threadpool(_build_zip, handle.name, entries)
    except Exception:
        os.remove(handle.name)
        raise

    return FileResponse(
        handle.name,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"{safe_filename(job.title, 'job')}_certificates.zip")},
        background=BackgroundTask(os.remove, handle.name),
    )


def _build_zip(target: str, entries: list[tuple[Path, str]]) -> None:
    # PDFs are already compressed, so store them; zipfile copies each file in chunks (never fully in RAM).
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for path, arcname in entries:
            archive.write(path, arcname=arcname)


@router.get("/{job_id}/certificates/{recipient_id}")
async def download_certificate(
    job_id: str,
    recipient_id: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    job = await _job_or_404(session, job_id, current_user)
    recipient = await job_service.get_recipient(session, job, recipient_id)
    if recipient is None or recipient.status != RecipientStatus.SUCCESS.value:
        raise HTTPException(status_code=404, detail="Certificate not available")
    path = job_service.resolve_certificate_path(recipient.certificate_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Certificate file not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(f"{safe_filename(recipient.name)}_certificate.pdf")},
    )
