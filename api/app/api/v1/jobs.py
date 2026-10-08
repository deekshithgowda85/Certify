import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.auth import get_current_user
from app.database import get_session
from app.models import Job, RecipientStatus, User
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobListResponse, JobResponse
from app.schemas.recipient import RecipientListResponse, RecipientOut
from app.services import job_service
from app.services import rate_limit
from app.config import settings
from app.api.v1.job_responses import (
    build_zip as _build_zip,
    content_disposition,
    job_response as _job_response,
    safe_filename,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger("certificate_api")
CurrentUser = Annotated[User, Depends(get_current_user)]


async def _job_or_404(session: AsyncSession, job_id: str, current_user: User) -> Job:
    job = await job_service.get_job(session, job_id, current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=202,
    summary="Create a bulk certificate job",
    responses={
        202: {"description": "Job accepted", "model": JobCreateResponse},
        422: {
            "description": "Invalid request or no valid recipients",
            "content": {
                "application/json": {
                    "examples": {
                        "no_valid_recipients": {
                            "summary": "All recipients failed validation",
                            "value": {"detail": [{"index": 0, "error": "email: value is not a valid email address"}]},
                        }
                    }
                }
            },
        },
        409: {"description": "Idempotency key reused with a different request", "content": {"application/json": {"example": {"detail": "Idempotency-Key was already used with a different request"}}}},
        429: {"description": "The user's job creation limit was exceeded", "content": {"application/json": {"example": {"detail": "Too many requests. Try again in 30 seconds."}}}},
        503: {"description": "The job was saved but could not be enqueued", "content": {"application/json": {"example": {"detail": "Could not enqueue job; please retry later"}}}},
    },
)
async def create_job(
    payload: JobCreateRequest,
    current_user: CurrentUser,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key", min_length=1, max_length=255)] = None,
    session: AsyncSession = Depends(get_session),
):
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key:
            raise HTTPException(status_code=422, detail="Idempotency-Key must not be blank")
    await rate_limit.enforce_rate_limit(
        "jobs:create", str(current_user.id), settings.JOB_RATE_LIMIT_PER_MINUTE
    )
    try:
        created = await job_service.create_job(
            session,
            payload.title,
            payload.recipients,
            current_user.id,
            idempotency_key,
            job_service.request_fingerprint(payload.title, payload.recipients),
        )
    except job_service.NoValidRecipientsError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors,
        )
    except job_service.IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if created.replayed:
        if created.enqueue_error:
            raise HTTPException(status_code=503, detail="Could not enqueue job; please retry later")
    else:
        try:
            await run_in_threadpool(job_service.enqueue_certificate_task, str(created.job_id))
        except Exception as exc:  # broker unreachable etc.
            logger.exception("Could not enqueue certificate job %s", created.job_id)
            await job_service.mark_job_failed(session, created.job_id, f"Could not enqueue job: {exc}")
            raise HTTPException(status_code=503, detail="Could not enqueue job; please retry later")

    return JobCreateResponse(
        job_id=created.job_id,
        status="PENDING",
        total_recipients=created.total,
        valid_recipients=created.valid,
        invalid_recipients=created.invalid,
    )


@router.get(
    "",
    response_model=JobListResponse,
    summary="List the current user's certificate jobs",
)
async def list_jobs(current_user: CurrentUser, session: AsyncSession = Depends(get_session)) -> JobListResponse:
    jobs = await job_service.list_jobs(session, current_user.id)
    return JobListResponse(jobs=[_job_response(job, recipient_id) for job, recipient_id in jobs])


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status and progress",
    responses={
        404: {"description": "Job not found", "content": {"application/json": {"example": {"detail": "Job not found"}}}},
    },
)
async def get_job(
    job_id: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    job = await _job_or_404(session, job_id, current_user)
    return _job_response(job)


@router.get(
    "/{job_id}/recipients",
    response_model=RecipientListResponse,
    summary="List recipient processing results",
    responses={
        404: {"description": "Job not found", "content": {"application/json": {"example": {"detail": "Job not found"}}}},
        422: {"description": "Invalid pagination or status filter", "content": {"application/json": {"example": {"detail": "Input should be 'PENDING', 'SUCCESS' or 'FAILED'"}}}},
    },
)
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
@router.get(
    "/{job_id}/certificates/download-all",
    response_class=FileResponse,
    summary="Download all successful certificates as a ZIP",
    responses={
        200: {
            "description": "ZIP archive of successful certificate PDFs",
            "content": {"application/zip": {"example": "PK binary ZIP archive"}},
        },
        404: {"description": "Job not found or no certificates are available", "content": {"application/json": {"example": {"detail": "No certificates available for this job"}}}},
    },
)
async def download_all(job_id: str, current_user: CurrentUser, session: AsyncSession = Depends(get_session)):
    job = await _job_or_404(session, job_id, current_user)
    recipients = await job_service.list_successful_recipients(session, job)

    entries: list[tuple[Path, str]] = []
    for recipient in recipients:
        path = job_service.resolve_certificate_path(recipient.certificate_path)
        if path is not None:
            arcname = f"{safe_filename(recipient.name)}_{recipient.id}.pdf"
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


@router.get(
    "/{job_id}/certificates/{recipient_id}",
    response_class=FileResponse,
    summary="Download a successful recipient certificate",
    responses={
        200: {
            "description": "PDF certificate attachment",
            "content": {"application/pdf": {"example": "%PDF-1.4 binary PDF"}},
        },
        404: {"description": "Job, recipient, or PDF not found", "content": {"application/json": {"example": {"detail": "Certificate not available"}}}},
    },
)
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
