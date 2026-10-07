import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from helpers import make_recipient, make_recipients


@pytest.mark.asyncio
async def test_create_job_success_small(create_job, enqueue_mock):
    response = await create_job(make_recipients(3), title="Python Bootcamp 2024")
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["status"] == "PENDING"
    assert body["total_recipients"] == 3
    assert body["valid_recipients"] == 3
    assert body["invalid_recipients"] == 0
    assert body["processing_mode"] is None
    enqueue_mock.assert_called_once_with(body["job_id"])


@pytest.mark.asyncio
async def test_create_job_invalid_email(create_job, client):
    recipients = [make_recipient(1), make_recipient(2, email="not-an-email")]
    response = await create_job(recipients)
    assert response.status_code == 202
    body = response.json()
    assert body["valid_recipients"] == 1
    assert body["invalid_recipients"] == 1

    failed = await client.get(f"/api/v1/jobs/{body['job_id']}/recipients", params={"status": "FAILED"})
    items = failed.json()["recipients"]
    assert len(items) == 1
    assert "email" in items[0]["error_message"]
    assert items[0]["certificate_url"] is None

    job = (await client.get(f"/api/v1/jobs/{body['job_id']}")).json()
    assert job["failed_count"] == 1 and job["processed_count"] == 1


@pytest.mark.asyncio
async def test_create_job_all_invalid(create_job, enqueue_mock):
    response = await create_job([make_recipient(1, email="bad"), make_recipient(2, name="")])
    assert response.status_code == 422
    enqueue_mock.assert_not_called()


@pytest.mark.asyncio
async def test_create_job_future_date_is_invalid(create_job):
    future = (date.today() + timedelta(days=30)).isoformat()
    response = await create_job([make_recipient(1), make_recipient(2, completion_date=future)])
    assert response.status_code == 202
    assert response.json()["invalid_recipients"] == 1


@pytest.mark.asyncio
async def test_create_job_requires_recipients(client):
    response = await client.post("/api/v1/jobs", json={"title": "x", "recipients": []})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_job_enqueue_failure_returns_503(create_job, enqueue_mock, client):
    enqueue_mock.side_effect = RuntimeError("broker down")
    response = await create_job(make_recipients(2))
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_get_job_not_found(client):
    assert (await client.get("/api/v1/jobs/nonexistent-uuid")).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_get_job_returns_fields(create_job, client):
    job_id = (await create_job(make_recipients(2), title="My Job")).json()["job_id"]
    body = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert body["job_id"] == job_id
    assert body["title"] == "My Job"
    assert body["status"] == "PENDING"
    assert body["processing_mode"] is None
    assert body["total_recipients"] == 2
    assert body["container_id"] is None
    assert body["created_at"] and body["updated_at"]


@pytest.mark.asyncio
async def test_get_job_recipients_paginated(create_job, client):
    job_id = (await create_job(make_recipients(25))).json()["job_id"]
    response = await client.get(f"/api/v1/jobs/{job_id}/recipients", params={"page": 1, "size": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 25
    assert body["page"] == 1 and body["size"] == 10
    assert len(body["recipients"]) == 10

    last = await client.get(f"/api/v1/jobs/{job_id}/recipients", params={"page": 3, "size": 10})
    assert len(last.json()["recipients"]) == 5


@pytest.mark.asyncio
async def test_recipients_invalid_status_filter(create_job, client):
    job_id = (await create_job(make_recipients(1))).json()["job_id"]
    response = await client.get(f"/api/v1/jobs/{job_id}/recipients", params={"status": "BOGUS"})
    assert response.status_code == 422


def _mark_success(sync_engine, job_id: str, storage_path: str, count: int = 1):
    """Pretend the dispatcher finished: write real files and flip rows to SUCCESS."""
    from pathlib import Path
    from sqlalchemy import select
    from app.models import Recipient

    ids = []
    with Session(sync_engine) as session:
        rows = session.execute(
            select(Recipient).where(Recipient.job_id == uuid.UUID(job_id)).order_by(Recipient.name)
        ).scalars().all()
        for row in rows[:count]:
            relative = f"{job_id}/{row.id}.pdf"
            target = Path(storage_path) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"%PDF-1.4 fake pdf for tests")
            row.status = "SUCCESS"
            row.certificate_path = relative
            ids.append(str(row.id))
        session.commit()
    return ids


@pytest.mark.asyncio
async def test_download_certificate(create_job, client, sync_engine, storage_path):
    job_id = (await create_job(make_recipients(2))).json()["job_id"]
    (recipient_id,) = _mark_success(sync_engine, job_id, storage_path, count=1)

    response = await client.get(f"/api/v1/jobs/{job_id}/certificates/{recipient_id}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert 'filename="Learner 0_certificate.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")

    listing = (await client.get(f"/api/v1/jobs/{job_id}/recipients", params={"status": "SUCCESS"})).json()
    assert listing["recipients"][0]["certificate_url"] == f"/api/v1/jobs/{job_id}/certificates/{recipient_id}"


@pytest.mark.asyncio
async def test_download_certificate_404_when_not_success(create_job, client):
    job_id = (await create_job(make_recipients(1))).json()["job_id"]
    listing = (await client.get(f"/api/v1/jobs/{job_id}/recipients")).json()
    recipient_id = listing["recipients"][0]["id"]
    response = await client.get(f"/api/v1/jobs/{job_id}/certificates/{recipient_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_all_zip(create_job, client, sync_engine, storage_path):
    import io
    import zipfile

    job_id = (await create_job(make_recipients(3), title="Zip Job")).json()["job_id"]
    _mark_success(sync_engine, job_id, storage_path, count=2)

    response = await client.get(f"/api/v1/jobs/{job_id}/certificates/download-all")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="Zip Job_certificates.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == 2
        assert all(n.endswith(".pdf") for n in archive.namelist())


@pytest.mark.asyncio
async def test_download_all_404_without_certificates(create_job, client):
    job_id = (await create_job(make_recipients(2))).json()["job_id"]
    response = await client.get(f"/api/v1/jobs/{job_id}/certificates/download-all")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health(client, monkeypatch):
    from app.api.v1 import health

    async def redis_ok():
        return True

    monkeypatch.setattr(health, "check_redis", redis_ok)
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok", "version": "1.0.0"}


@pytest.mark.asyncio
async def test_health_degraded_when_redis_down(client, monkeypatch):
    from app.api.v1 import health

    async def redis_down():
        return False

    monkeypatch.setattr(health, "check_redis", redis_down)
    response = await client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["redis"] == "error"
