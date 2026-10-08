import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.batch_responses import combined_pdf_response
from app.auth import get_current_user
from app.database import get_session
from app.models import JobBatch, RecipientStatus, User
from app.schemas.job import (
    JobBatchCreateRequest,
    JobBatchCreateResponse,
    JobBatchRegenerateResponse,
    JobBatchResponse,
)
from app.schemas.recipient import RecipientListResponse, RecipientOut
from app.services import batch_service, job_service, rate_limit
from app.config import settings

router = APIRouter(prefix="/jobs/batches", tags=["job batches"])
logger = logging.getLogger("certificate_api")
CurrentUser = Annotated[User, Depends(get_current_user)]


async def _batch_or_404(session: AsyncSession, batch_id: str, user_id) -> JobBatch:
    batch = await batch_service.get_batch(session, batch_id, user_id, public=False)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.post("", response_model=JobBatchCreateResponse, status_code=202)
async def create_batch(
    payload: JobBatchCreateRequest,
    current_user: CurrentUser,
    idempotency_key: Annotated[
        Optional[str], Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
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
        created = await batch_service.create_batch(
            session, payload.title, payload.recipients, current_user.id, idempotency_key
        )
    except batch_service.BatchIdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if not created.replayed:
        for child in created.jobs:
            if not child.valid:
                continue
            try:
                await run_in_threadpool(job_service.enqueue_certificate_task, str(child.job_id))
            except Exception as exc:
                logger.exception("Could not enqueue certificate job %s in batch %s", child.job_id, created.batch_id)
                await job_service.mark_job_failed(
                    session, child.job_id, f"Could not enqueue job: {exc}"
                )

    return JobBatchCreateResponse(
        batch_id=created.batch_id,
        status="PENDING" if created.valid else "FAILED",
        total_recipients=created.total,
        valid_recipients=created.valid,
        invalid_recipients=created.invalid,
        job_count=len(created.jobs),
    )


@router.get("/{batch_id}", response_model=JobBatchResponse)
async def get_batch(
    batch_id: str, current_user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    batch = await _batch_or_404(session, batch_id, current_user.id)
    jobs = await batch_service.batch_jobs(session, batch)
    return batch_service.batch_response(batch, jobs)


@router.get("/{batch_id}/recipients", response_model=RecipientListResponse)
async def list_recipients(
    batch_id: str,
    current_user: CurrentUser,
    status: Optional[RecipientStatus] = Query(default=RecipientStatus.FAILED),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    batch = await _batch_or_404(session, batch_id, current_user.id)
    total, recipients = await batch_service.list_failed_recipients(
        session, batch, page, size, status.value if status else None
    )
    return RecipientListResponse(
        job_id=batch.id,
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
                certificate_url=None,
            )
            for recipient in recipients
        ],
    )


@router.get("/{batch_id}/certificates/download-all", response_class=FileResponse)
async def download_batch_certificates(
    batch_id: str, current_user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    batch = await _batch_or_404(session, batch_id, current_user.id)
    return await combined_pdf_response(session, batch)


@router.post("/{batch_id}/regenerate", response_model=JobBatchRegenerateResponse, status_code=202)
async def regenerate_batch_certificates(
    batch_id: str, current_user: CurrentUser, session: AsyncSession = Depends(get_session)
):
    await rate_limit.enforce_rate_limit(
        "jobs:regenerate", str(current_user.id), settings.JOB_RATE_LIMIT_PER_MINUTE
    )
    batch = await _batch_or_404(session, batch_id, current_user.id)
    try:
        regeneration = await batch_service.prepare_batch_regeneration(session, batch)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    for job in regeneration.jobs:
        try:
            await run_in_threadpool(job_service.enqueue_certificate_task, str(job.id))
        except Exception as exc:
            logger.exception("Could not re-enqueue certificate job %s in batch %s", job.id, batch.id)
            await job_service.mark_job_failed(session, job.id, f"Could not enqueue job: {exc}")

    return JobBatchRegenerateResponse(
        batch_id=batch.id,
        status="PENDING",
        recipients_to_regenerate=regeneration.recipients_to_regenerate,
        job_count=len(regeneration.jobs),
    )
