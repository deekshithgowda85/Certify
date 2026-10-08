import io
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from helpers import make_recipient, make_recipients


@pytest.mark.asyncio
async def test_public_job_can_be_created_and_tracked_without_auth(
    anonymous_client, enqueue_mock, client
):
    created = await anonymous_client.post(
        "/api/v1/public/jobs",
        json={"title": "Guest batch", "recipients": make_recipients(3)},
    )
    assert created.status_code == 202
    body = created.json()
    assert body["total_recipients"] == body["valid_recipients"] == 3
    enqueue_mock.assert_called_once_with(body["job_id"])

    status = await anonymous_client.get(f"/api/v1/public/jobs/{body['job_id']}")
    assert status.status_code == 200
    assert status.json()["status"] == "PENDING"

    recipients = await anonymous_client.get(
        f"/api/v1/public/jobs/{body['job_id']}/recipients",
        params={"page": 1, "size": 2},
    )
    assert recipients.status_code == 200
    assert recipients.json()["total"] == 3
    assert len(recipients.json()["recipients"]) == 2

    assert (await client.get(f"/api/v1/jobs/{body['job_id']}")).status_code == 404
    assert (await anonymous_client.get("/api/v1/jobs")).status_code == 401


@pytest.mark.asyncio
async def test_public_job_creation_keeps_recipient_validation(enqueue_mock, anonymous_client):
    response = await anonymous_client.post(
        "/api/v1/public/jobs",
        json={
            "title": "Mixed anonymous batch",
            "recipients": [make_recipient(1), make_recipient(2, email="invalid")],
        },
    )
    assert response.status_code == 202
    assert response.json()["valid_recipients"] == 1
    assert response.json()["invalid_recipients"] == 1
    enqueue_mock.assert_called_once_with(response.json()["job_id"])


@pytest.mark.asyncio
async def test_public_job_id_is_required_to_view_anonymous_jobs(anonymous_client, client):
    response = await client.post(
        "/api/v1/jobs",
        json={"title": "Private account job", "recipients": make_recipients(1)},
    )
    job_id = response.json()["job_id"]
    assert (await anonymous_client.get(f"/api/v1/public/jobs/{job_id}")).status_code == 404
    assert (await anonymous_client.get("/api/v1/public/jobs/not-a-uuid")).status_code == 404


@pytest.mark.asyncio
async def test_public_job_can_download_successful_pdf_and_zip(
    anonymous_client, enqueue_mock, storage_path, sync_engine
):
    from app.models import Job, Recipient

    response = await anonymous_client.post(
        "/api/v1/public/jobs",
        json={"title": "Public Certificates", "recipients": make_recipients(1)},
    )
    job_id = uuid.UUID(response.json()["job_id"])
    enqueue_mock.assert_called_once_with(str(job_id))

    with Session(sync_engine) as session:
        job = session.get(Job, job_id)
        recipient = session.scalar(select(Recipient).where(Recipient.job_id == job_id))
        relative_path = f"{job_id}/{recipient.id}.pdf"
        pdf_path = Path(storage_path) / relative_path
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 test certificate")
        recipient.status = "SUCCESS"
        recipient.certificate_path = relative_path
        job.processed_count = 1
        job.success_count = 1
        job.status = "COMPLETED"
        session.commit()
        recipient_id = str(recipient.id)

    item_list = await anonymous_client.get(
        f"/api/v1/public/jobs/{job_id}/recipients",
        params={"status": "SUCCESS"},
    )
    assert item_list.status_code == 200
    assert item_list.json()["recipients"][0]["certificate_url"] == (
        f"/api/v1/public/jobs/{job_id}/certificates/{recipient_id}"
    )

    pdf = await anonymous_client.get(
        f"/api/v1/public/jobs/{job_id}/certificates/{recipient_id}"
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")

    archive_response = await anonymous_client.get(
        f"/api/v1/public/jobs/{job_id}/certificates/download-all"
    )
    assert archive_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
        assert len(archive.namelist()) == 1
        assert archive.read(archive.namelist()[0]).startswith(b"%PDF-")
