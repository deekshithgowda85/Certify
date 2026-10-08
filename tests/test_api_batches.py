import uuid
import os
import time

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from helpers import make_recipient


@pytest.mark.asyncio
async def test_large_batch_is_split_and_tracked_as_one_submission(
    client, enqueue_mock, sync_engine, monkeypatch
):
    from app.config import settings
    from app.models import Job, Recipient

    monkeypatch.setattr(settings, "MAX_RECIPIENTS_PER_JOB", 2)
    recipients = [
        make_recipient(1),
        make_recipient(2, email="invalid-email"),
        make_recipient(3),
    ]
    response = await client.post(
        "/api/v1/jobs/batches",
        json={"title": "Large class", "recipients": recipients},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["total_recipients"] == 3
    assert body["valid_recipients"] == 2
    assert body["invalid_recipients"] == 1
    assert body["job_count"] == 2
    assert enqueue_mock.call_count == 2

    batch_id = uuid.UUID(body["batch_id"])
    with Session(sync_engine) as session:
        jobs = session.scalars(select(Job).where(Job.batch_id == batch_id)).all()
        assert len(jobs) == 2
        assert [job.total_recipients for job in jobs] == [2, 1]
        source_indexes = session.scalars(
            select(Recipient.source_index).join(Job).where(Job.batch_id == batch_id)
        ).all()
        assert sorted(source_indexes) == [0, 1, 2]

    status = await client.get(f"/api/v1/jobs/batches/{batch_id}")
    assert status.status_code == 200
    assert status.json()["total_recipients"] == 3

    failed = await client.get(
        f"/api/v1/jobs/batches/{batch_id}/recipients",
        params={"status": "FAILED"},
    )
    assert failed.status_code == 200
    assert failed.json()["total"] == 1
    assert failed.json()["recipients"][0]["name"] == recipients[1]["name"]


@pytest.mark.asyncio
async def test_all_invalid_batch_is_tracked_without_queueing(
    client, enqueue_mock
):
    response = await client.post(
        "/api/v1/jobs/batches",
        json={
            "title": "Invalid rows",
            "recipients": [make_recipient(1, email="not-an-email")],
        },
    )
    assert response.status_code == 202
    assert response.json()["valid_recipients"] == 0
    assert response.json()["invalid_recipients"] == 1
    enqueue_mock.assert_not_called()

    status = await client.get(f"/api/v1/jobs/batches/{response.json()['batch_id']}")
    assert status.status_code == 200
    assert status.json()["status"] == "FAILED"


@pytest.mark.asyncio
async def test_authenticated_batch_idempotency_prevents_duplicate_jobs(client, enqueue_mock):
    payload = {"title": "Idempotent batch", "recipients": [make_recipient(1)]}
    headers = {"Idempotency-Key": "stable-batch-request"}

    first = await client.post("/api/v1/jobs/batches", json=payload, headers=headers)
    replay = await client.post("/api/v1/jobs/batches", json=payload, headers=headers)

    assert first.status_code == replay.status_code == 202
    assert replay.json()["batch_id"] == first.json()["batch_id"]
    enqueue_mock.assert_called_once()


@pytest.mark.asyncio
async def test_public_batch_can_be_tracked_without_authentication(anonymous_client, enqueue_mock):
    response = await anonymous_client.post(
        "/api/v1/public/batches",
        json={"title": "Public batch", "recipients": [make_recipient(1)]},
    )

    assert response.status_code == 202
    batch_id = response.json()["batch_id"]
    status = await anonymous_client.get(f"/api/v1/public/batches/{batch_id}")
    assert status.status_code == 200
    assert status.json()["total_recipients"] == 1
    enqueue_mock.assert_called_once()


def test_merge_pdfs_combines_all_source_pages(tmp_path):
    from pypdf import PdfReader, PdfWriter

    from app.api.v1.batch_responses import merge_pdfs

    sources = []
    for index in range(3):
        source = tmp_path / f"certificate-{index}.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with source.open("wb") as output:
            writer.write(output)
        sources.append(source)

    target = tmp_path / "combined.pdf"
    merge_pdfs(str(target), sources)

    assert len(PdfReader(target).pages) == len(sources)


def test_batch_request_allows_exactly_up_to_one_hundred_thousand():
    from pydantic import ValidationError

    from app.schemas.job import JobBatchCreateRequest

    assert len(
        JobBatchCreateRequest(title="Maximum batch", recipients=[{}] * 100000).recipients
    ) == 100000
    with pytest.raises(ValidationError):
        JobBatchCreateRequest(title="Too large", recipients=[{}] * 100001)


def test_certificate_cleanup_removes_only_pdfs_older_than_the_ttl(tmp_path):
    from app.services.certificate_storage import cleanup_expired_certificates

    storage = tmp_path / "storage"
    nested = storage / "job"
    nested.mkdir(parents=True)
    expired_pdf = nested / "expired.pdf"
    fresh_pdf = nested / "fresh.pdf"
    non_pdf = nested / "keep.txt"
    expired_pdf.write_bytes(b"expired")
    fresh_pdf.write_bytes(b"fresh")
    non_pdf.write_bytes(b"keep")
    now = time.time()
    os.utime(expired_pdf, (now - 601, now - 601))
    os.utime(fresh_pdf, (now - 599, now - 599))

    deleted, bytes_freed = cleanup_expired_certificates(storage, ttl_seconds=600, now=now)

    assert (deleted, bytes_freed) == (1, len(b"expired"))
    assert not expired_pdf.exists()
    assert fresh_pdf.exists()
    assert non_pdf.exists()


@pytest.mark.asyncio
async def test_expired_batch_pdfs_can_be_regenerated(client, enqueue_mock, sync_engine):
    from app.models import Job, Recipient

    created = await client.post(
        "/api/v1/jobs/batches",
        json={"title": "Regenerate batch", "recipients": [make_recipient(1)]},
    )
    assert created.status_code == 202
    batch_id = created.json()["batch_id"]

    with Session(sync_engine) as session:
        job = session.scalar(select(Job).where(Job.batch_id == uuid.UUID(batch_id)))
        recipient = session.scalar(select(Recipient).where(Recipient.job_id == job.id))
        job.status = "COMPLETED"
        job.processed_count = 1
        job.success_count = 1
        recipient.status = "SUCCESS"
        recipient.certificate_path = f"{job.id}/{recipient.id}.pdf"
        session.commit()

    missing_pdf = await client.get(
        f"/api/v1/jobs/batches/{batch_id}/certificates/download-all"
    )
    assert missing_pdf.status_code == 410
    assert "Regenerate this batch" in missing_pdf.json()["detail"]

    enqueue_mock.reset_mock()
    regenerated = await client.post(f"/api/v1/jobs/batches/{batch_id}/regenerate")
    assert regenerated.status_code == 202
    assert regenerated.json()["recipients_to_regenerate"] == 1
    assert regenerated.json()["job_count"] == 1
    enqueue_mock.assert_called_once()

    with Session(sync_engine) as session:
        job = session.scalar(select(Job).where(Job.batch_id == uuid.UUID(batch_id)))
        recipient = session.scalar(select(Recipient).where(Recipient.job_id == job.id))
        assert job.status == "PENDING"
        assert job.success_count == 0
        assert recipient.status == "PENDING"
        assert recipient.certificate_path is None
