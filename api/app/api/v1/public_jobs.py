import logging
import os
import tempfile
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.v1.job_responses import build_zip, content_disposition, job_response, safe_filename
from app.config import settings
from app.database import get_session
from app.models import Job, RecipientStatus
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobResponse
from app.schemas.recipient import RecipientListResponse, RecipientOut
from app.services import job_service, rate_limit

router = APIRouter(prefix="/public/jobs", tags=["public bulk jobs"])
logger = logging.getLogger("certificate_api")


async def _public_job_or_404(session: AsyncSession, job_id: str) -> Job:
    job = await job_service.get_public_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=202,
    summary="Create a bulk certificate job without an account",
    responses={
        202: {"description": "Job accepted"},
        422: {"description": "Invalid request or no valid recipients"},
        429: {"description": "Anonymous job creation limit exceeded"},
        503: {"description": "Job could not be enqueued"},
    },
)
async def create_public_job(
    payload: JobCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    await rate_limit.enforce_rate_limit(
        "public-jobs:create",
        rate_limit.client_ip(request),
        settings.PUBLIC_JOB_RATE_LIMIT_PER_MINUTE,
    )
    try:
        created = await job_service.create_job(
            session,
            payload.title,
            payload.recipients,
            user_id=None,
        )
    except job_service.NoValidRecipientsError as exc:
        raise HTTPException(status_code=422, detail=exc.errors)

    try:
        await run_in_threadpool(job_service.enqueue_certificate_task, str(created.job_id))
    except Exception as exc:
        logger.exception("Could not enqueue public certificate job %s", created.job_id)
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
    "/{job_id}",
    response_model=JobResponse,
    summary="Get anonymous job progress",
    responses={404: {"description": "Job not found"}},
)
async def get_public_job(job_id: str, session: AsyncSession = Depends(get_session)):
    job = await _public_job_or_404(session, job_id)
    return job_response(job)


@router.get(
    "/{job_id}/recipients",
    response_model=RecipientListResponse,
    summary="List anonymous job recipient results",
    responses={
        404: {"description": "Job not found"},
        422: {"description": "Invalid pagination or status filter"},
    },
)
async def list_public_recipients(
    job_id: str,
    status: Optional[Literal["PENDING", "SUCCESS", "FAILED"]] = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    job = await _public_job_or_404(session, job_id)
    total, rows = await job_service.list_recipients(session, job, status, page, size)
    return RecipientListResponse(
        job_id=job.id,
        total=total,
        page=page,
        size=size,
        recipients=[
            RecipientOut(
                id=recipient.id,
                name=recipient.name,
                email=recipient.email,
                status=recipient.status,
                error_message=recipient.error_message,
                certificate_url=(
                    f"/api/v1/public/jobs/{job.id}/certificates/{recipient.id}"
                    if recipient.status == RecipientStatus.SUCCESS.value
                    else None
                ),
            )
            for recipient in rows
        ],
    )


@router.get(
    "/{job_id}/certificates/download-all",
    response_class=FileResponse,
    summary="Download anonymous job certificates as a ZIP",
    responses={
        200: {"description": "ZIP archive of successful certificate PDFs"},
        404: {"description": "Job not found or no successful certificates"},
    },
)
async def download_public_all(job_id: str, session: AsyncSession = Depends(get_session)):
    job = await _public_job_or_404(session, job_id)
    recipients = await job_service.list_successful_recipients(session, job)
    entries: list[tuple[Path, str]] = []
    for recipient in recipients:
        path = job_service.resolve_certificate_path(recipient.certificate_path)
        if path is not None:
            entries.append((path, f"{safe_filename(recipient.name)}_{recipient.id}.pdf"))
    if not entries:
        raise HTTPException(status_code=404, detail="No certificates available for this job")

    handle = tempfile.NamedTemporaryFile(prefix="certificates_", suffix=".zip", delete=False)
    handle.close()
    try:
        await run_in_threadpool(build_zip, handle.name, entries)
    except Exception:
        os.remove(handle.name)
        raise

    return FileResponse(
        handle.name,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition(
                f"{safe_filename(job.title, 'job')}_certificates.zip"
            )
        },
        background=BackgroundTask(os.remove, handle.name),
    )


@router.get(
    "/{job_id}/certificates/{recipient_id}",
    response_class=FileResponse,
    summary="Download an anonymous recipient certificate",
    responses={
        200: {"description": "PDF certificate attachment"},
        404: {"description": "Job, recipient, or PDF not found"},
    },
)
async def download_public_certificate(
    job_id: str,
    recipient_id: str,
    session: AsyncSession = Depends(get_session),
):
    job = await _public_job_or_404(session, job_id)
    recipient = await job_service.get_recipient(session, job, recipient_id)
    if recipient is None or recipient.status != RecipientStatus.SUCCESS.value:
        raise HTTPException(status_code=404, detail="Certificate not available")
    path = job_service.resolve_certificate_path(recipient.certificate_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Certificate file not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(
                f"{safe_filename(recipient.name)}_certificate.pdf"
            )
        },
    )
