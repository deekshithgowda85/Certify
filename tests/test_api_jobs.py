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
    assert body["message"]
    assert set(body) == {
        "job_id",
        "status",
        "total_recipients",
        "valid_recipients",
        "invalid_recipients",
        "message",
    }
    enqueue_mock.assert_called_once_with(body["job_id"])


@pytest.mark.asyncio
async def test_idempotency_key_replays_job_without_enqueuing_twice(client, enqueue_mock):
    payload = {"title": "Same request", "recipients": make_recipients(2)}
    headers = {"Idempotency-Key": "stable-request-1"}

    first = await client.post("/api/v1/jobs", json=payload, headers=headers)
    second = await client.post("/api/v1/jobs", json=payload, headers=headers)

    assert first.status_code == second.status_code == 202
    assert second.json() == first.json()
    enqueue_mock.assert_called_once_with(first.json()["job_id"])


@pytest.mark.asyncio
async def test_idempotency_key_rejects_changed_payload(client, enqueue_mock):
    headers = {"Idempotency-Key": "stable-request-2"}
    first = await client.post(
        "/api/v1/jobs",
        json={"title": "Original", "recipients": make_recipients(1)},
        headers=headers,
    )
    changed = await client.post(
        "/api/v1/jobs",
        json={"title": "Changed", "recipients": make_recipients(1)},
        headers=headers,
    )

    assert first.status_code == 202
    assert changed.status_code == 409
    assert changed.json()["detail"] == "Idempotency-Key was already used with a different request"
    enqueue_mock.assert_called_once()


@pytest.mark.asyncio
async def test_idempotency_key_replays_enqueue_failure_without_duplicate_job(
    client, enqueue_mock, sync_engine
):
    enqueue_mock.side_effect = RuntimeError("broker down")
    headers = {"Idempotency-Key": "stable-request-3"}
    payload = {"title": "Enqueue failure", "recipients": make_recipients(1)}

    first = await client.post("/api/v1/jobs", json=payload, headers=headers)
    second = await client.post("/api/v1/jobs", json=payload, headers=headers)

    assert first.status_code == second.status_code == 503
    enqueue_mock.assert_called_once()
    assert len((await client.get("/api/v1/jobs")).json()["jobs"]) == 1


@pytest.mark.asyncio
async def test_job_rows_are_committed_before_enqueue(client, enqueue_mock, sync_engine):
    from app.models import Job

    observed = []

    def verify_committed(job_id):
        with Session(sync_engine) as session:
            observed.append(session.get(Job, uuid.UUID(job_id)) is not None)

    enqueue_mock.side_effect = verify_committed
    response = await client.post(
        "/api/v1/jobs",
        json={"title": "Committed first", "recipients": make_recipients(2)},
    )
    assert response.status_code == 202
    assert observed == [True]
    enqueue_mock.assert_called_once_with(response.json()["job_id"])


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
async def test_create_job_all_invalid(create_job, enqueue_mock, client):
    response = await create_job([make_recipient(1, email="bad"), make_recipient(2, name="")])
    assert response.status_code == 422
    assert [item["index"] for item in response.json()["detail"]] == [0, 1]
    assert all(item["error"] for item in response.json()["detail"])
    enqueue_mock.assert_not_called()
    assert (await client.get("/api/v1/jobs")).json()["jobs"] == []


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
async def test_create_job_enqueue_failure_returns_503(create_job, enqueue_mock, client, caplog):
    enqueue_mock.side_effect = RuntimeError("broker down")
    response = await create_job(make_recipients(2))
    assert response.status_code == 503
    assert response.json() == {"detail": "Could not enqueue job; please retry later"}
    enqueue_mock.assert_called_once()
    job_id = enqueue_mock.call_args.args[0]
    assert job_id in caplog.text
    job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert job["status"] == "FAILED"
    assert job["failed_count"] == job["processed_count"] == 2
    recipients = (await client.get(f"/api/v1/jobs/{job_id}/recipients")).json()["recipients"]
    assert all(row["status"] == "FAILED" and "enqueue" in row["error_message"] for row in recipients)


@pytest.mark.asyncio
async def test_create_job_with_50_recipients(create_job, enqueue_mock):
    response = await create_job(make_recipients(50))
    assert response.status_code == 202
    assert response.json()["total_recipients"] == 50
    assert response.json()["valid_recipients"] == 50
    enqueue_mock.assert_called_once_with(response.json()["job_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "remove", "expected_field"),
    [
        ({"name": ""}, None, "name"),
        ({"name": "x" * 256}, None, "name"),
        ({"email": "not-an-email"}, None, "email"),
        ({}, "course_name", "course_name"),
        ({"course_name": "   "}, None, "course_name"),
        ({}, "completion_date", "completion_date"),
        ({"completion_date": (date.today() + timedelta(days=1)).isoformat()}, None, "completion_date"),
        ({"completion_date": "2026-13-01"}, None, "completion_date"),
        ({"name": 123}, None, "name"),
        ({"email": 123}, None, "email"),
        ({"course_name": ["course"]}, None, "course_name"),
        ({"completion_date": 123}, None, "completion_date"),
    ],
)
async def test_invalid_recipient_is_saved_as_failed(
    client, enqueue_mock, overrides, remove, expected_field
):
    invalid = make_recipient(0, **overrides)
    if remove:
        invalid.pop(remove)
    response = await client.post(
        "/api/v1/jobs",
        json={"title": "Validation job", "recipients": [make_recipient(1), invalid]},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["valid_recipients"] == 1
    assert body["invalid_recipients"] == 1
    failed = await client.get(
        f"/api/v1/jobs/{body['job_id']}/recipients", params={"status": "FAILED"}
    )
    assert failed.status_code == 200
    assert len(failed.json()["recipients"]) == 1
    assert expected_field in failed.json()["recipients"][0]["error_message"]
    enqueue_mock.assert_called_once_with(body["job_id"])


@pytest.mark.asyncio
async def test_recipient_item_must_be_object_but_does_not_reject_bulk_request(client):
    response = await client.post(
        "/api/v1/jobs",
        json={"title": "Mixed", "recipients": [make_recipient(1), "not-an-object"]},
    )
    assert response.status_code == 202
    assert response.json()["valid_recipients"] == 1
    assert response.json()["invalid_recipients"] == 1


@pytest.mark.asyncio
async def test_wrong_request_field_types_are_json_422_and_not_enqueued(client, enqueue_mock):
    for body in (
        {"title": "Wrong", "recipients": "not-a-list"},
        {"title": 123, "recipients": [make_recipient(1)]},
        {"title": "Wrong", "recipients": None},
    ):
        response = await client.post("/api/v1/jobs", json=body)
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)
    enqueue_mock.assert_not_called()


@pytest.mark.asyncio
async def test_empty_recipients_list_is_rejected(client):
    response = await client.post("/api/v1/jobs", json={"title": "Empty", "recipients": []})
    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_malformed_json_is_a_json_422(client):
    response = await client.post(
        "/api/v1/jobs",
        content="{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.asyncio
async def test_get_job_not_found(client):
    malformed = await client.get("/api/v1/jobs/nonexistent-uuid")
    unknown = await client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert malformed.status_code == unknown.status_code == 404
    assert malformed.json() == unknown.json() == {"detail": "Job not found"}


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
    assert "recipient_id" not in body


@pytest.mark.asyncio
async def test_job_status_and_counters_follow_processing_outcomes(create_job, client, sync_engine):
    from app.models import Job, Recipient

    expected = [
        ("COMPLETED", 3, 0),
        ("PARTIALLY_FAILED", 1, 2),
        ("FAILED", 0, 3),
    ]
    for index, (status, successes, failures) in enumerate(expected):
        job_id = (await create_job(make_recipients(3), title=f"Outcome {index}")).json()["job_id"]
        with Session(sync_engine) as session:
            job = session.get(Job, uuid.UUID(job_id))
            rows = (
                session.query(Recipient)
                .filter(Recipient.job_id == uuid.UUID(job_id))
                .order_by(Recipient.name)
                .all()
            )
            job.status = status
            job.processed_count = successes + failures
            job.success_count = successes
            job.failed_count = failures
            for row_index, row in enumerate(rows):
                row.status = "SUCCESS" if row_index < successes else "FAILED"
            session.commit()

        body = (await client.get(f"/api/v1/jobs/{job_id}")).json()
        assert body["status"] == status
        assert body["processed_count"] == successes + failures
        assert body["success_count"] == successes
        assert body["failed_count"] == failures


@pytest.mark.asyncio
async def test_get_job_recipients_paginated(create_job, client):
    job_id = (await create_job(make_recipients(25))).json()["job_id"]
    response = await client.get(f"/api/v1/jobs/{job_id}/recipients", params={"page": 1, "size": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 25
    assert body["page"] == 1 and body["size"] == 10
    assert len(body["recipients"]) == 10

    middle = await client.get(f"/api/v1/jobs/{job_id}/recipients", params={"page": 2, "size": 10})
    assert len(middle.json()["recipients"]) == 10

    last = await client.get(f"/api/v1/jobs/{job_id}/recipients", params={"page": 3, "size": 10})
    assert len(last.json()["recipients"]) == 5


@pytest.mark.asyncio
async def test_recipients_invalid_status_filter(create_job, client):
    job_id = (await create_job(make_recipients(1))).json()["job_id"]
    response = await client.get(f"/api/v1/jobs/{job_id}/recipients", params={"status": "BOGUS"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recipient_status_filter_returns_only_matching_rows(create_job, client, sync_engine, storage_path):
    job_id = (await create_job([make_recipient(0), make_recipient(1, email="bad")])).json()["job_id"]
    _mark_success(sync_engine, job_id, storage_path, count=1)
    for status, expected_count in (("SUCCESS", 1), ("FAILED", 1), ("PENDING", 0)):
        response = await client.get(
            f"/api/v1/jobs/{job_id}/recipients", params={"status": status}
        )
        assert response.status_code == 200
        assert response.json()["total"] == expected_count
        assert len(response.json()["recipients"]) == expected_count


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"page": 0}, {"size": 0}, {"size": 101}])
async def test_recipients_reject_invalid_pagination(create_job, client, params):
    job_id = (await create_job(make_recipients(1))).json()["job_id"]
    response = await client.get(f"/api/v1/jobs/{job_id}/recipients", params=params)
    assert response.status_code == 422
    assert "detail" in response.json()


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
async def test_download_filename_has_safe_ascii_and_utf8_forms(create_job, client, sync_engine, storage_path):
    from sqlalchemy import select

    from app.models import Recipient

    job_id = (await create_job(make_recipients(1))).json()["job_id"]
    (recipient_id,) = _mark_success(sync_engine, job_id, storage_path, count=1)
    with Session(sync_engine) as session:
        row = session.execute(select(Recipient).where(Recipient.id == uuid.UUID(recipient_id))).scalar_one()
        row.name = "Éda Lovelace"
        session.commit()
    response = await client.get(f"/api/v1/jobs/{job_id}/certificates/{recipient_id}")
    disposition = response.headers["content-disposition"]
    assert 'filename="da Lovelace_certificate.pdf"' in disposition
    assert "filename*=utf-8''%C3%89da%20Lovelace_certificate.pdf" in disposition


@pytest.mark.asyncio
async def test_download_certificate_404_when_not_success(create_job, client):
    job_id = (await create_job(make_recipients(1))).json()["job_id"]
    listing = (await client.get(f"/api/v1/jobs/{job_id}/recipients")).json()
    recipient_id = listing["recipients"][0]["id"]
    response = await client.get(f"/api/v1/jobs/{job_id}/certificates/{recipient_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_certificate_404_for_bad_id_and_missing_file(
    create_job, client, sync_engine, storage_path
):
    from pathlib import Path
    from sqlalchemy import select

    from app.models import Recipient

    job_id = (await create_job(make_recipients(1))).json()["job_id"]
    assert (await client.get(f"/api/v1/jobs/{job_id}/certificates/bad-id")).status_code == 404
    (recipient_id,) = _mark_success(sync_engine, job_id, storage_path, count=1)
    with Session(sync_engine) as session:
        row = session.execute(select(Recipient).where(Recipient.id == uuid.UUID(recipient_id))).scalar_one()
        (Path(storage_path) / row.certificate_path).unlink()
    missing = await client.get(f"/api/v1/jobs/{job_id}/certificates/{recipient_id}")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Certificate file not found"}


@pytest.mark.asyncio
async def test_download_certificate_refuses_path_traversal(create_job, client, sync_engine, storage_path):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.models import Recipient

    job_id = (await create_job(make_recipients(1))).json()["job_id"]
    (recipient_id,) = _mark_success(sync_engine, job_id, storage_path, count=1)
    with Session(sync_engine) as session:
        row = session.execute(select(Recipient).where(Recipient.id == uuid.UUID(recipient_id))).scalar_one()
        row.certificate_path = "../outside.pdf"
        session.commit()
    response = await client.get(f"/api/v1/jobs/{job_id}/certificates/{recipient_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_certificate_must_belong_to_requested_job(
    create_job, client, sync_engine, storage_path
):
    first_job = (await create_job(make_recipients(1), title="First")).json()["job_id"]
    second_job = (await create_job(make_recipients(1), title="Second")).json()["job_id"]
    (recipient_id,) = _mark_success(sync_engine, first_job, storage_path, count=1)
    response = await client.get(f"/api/v1/jobs/{second_job}/certificates/{recipient_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Certificate not available"}


@pytest.mark.asyncio
async def test_download_all_zip(create_job, client, sync_engine, storage_path):
    import io
    import zipfile

    job_id = (await create_job(make_recipients(3), title="Zip Job")).json()["job_id"]

    from app.models import Recipient

    with Session(sync_engine) as session:
        rows = (
            session.query(Recipient)
            .filter(Recipient.job_id == uuid.UUID(job_id))
            .order_by(Recipient.name)
            .all()
        )
        for row in rows[:2]:
            row.name = "Same Name"
        session.commit()
    _mark_success(sync_engine, job_id, storage_path, count=2)

    response = await client.get(f"/api/v1/jobs/{job_id}/certificates/download-all")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="Zip Job_certificates.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == 2
        assert all(n.endswith(".pdf") for n in archive.namelist())
        assert len(archive.namelist()) == len(set(archive.namelist()))


@pytest.mark.asyncio
async def test_download_all_temp_archive_is_deleted_after_response(
    create_job, client, sync_engine, storage_path, monkeypatch, tmp_path
):
    import tempfile

    job_id = (await create_job(make_recipients(1), title="Temporary")).json()["job_id"]
    _mark_success(sync_engine, job_id, storage_path, count=1)
    original_named_temporary_file = tempfile.NamedTemporaryFile

    def make_temp_file(*, prefix, suffix, delete):
        return original_named_temporary_file(
            dir=tmp_path, prefix=f"response_{prefix}", suffix=suffix, delete=delete
        )

    monkeypatch.setattr("app.api.v1.jobs.tempfile.NamedTemporaryFile", make_temp_file)
    response = await client.get(f"/api/v1/jobs/{job_id}/certificates/download-all")
    assert response.status_code == 200
    assert not list(tmp_path.glob("response_certificates_*.zip"))


@pytest.mark.asyncio
async def test_download_all_404_without_certificates(create_job, client):
    job_id = (await create_job(make_recipients(2))).json()["job_id"]
    response = await client.get(f"/api/v1/jobs/{job_id}/certificates/download-all")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health(client, monkeypatch):
    from app.api.v1 import health

    async def broker_ok():
        return True

    monkeypatch.setattr(health, "check_broker", broker_ok)
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "broker": "ok", "version": "1.0.0"}


@pytest.mark.asyncio
async def test_health_degraded_when_broker_down(client, monkeypatch):
    from app.api.v1 import health

    async def broker_down():
        return False

    monkeypatch.setattr(health, "check_broker", broker_down)
    response = await client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["broker"] == "error"


@pytest.mark.asyncio
async def test_health_degraded_when_database_down(client, monkeypatch):
    from app.api.v1 import health

    async def db_down():
        return False

    async def broker_ok():
        return True

    monkeypatch.setattr(health, "check_db", db_down)
    monkeypatch.setattr(health, "check_broker", broker_ok)
    response = await client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["db"] == "error"
    assert response.json()["broker"] == "ok"


@pytest.mark.asyncio
async def test_unexpected_errors_have_clean_json(client, monkeypatch):
    from app.services import job_service

    async def fail_create():
        raise RuntimeError("internal detail should not be exposed")

    monkeypatch.setattr(job_service, "create_job", fail_create)
    response = await client.post(
        "/api/v1/jobs",
        json={"title": "Failure", "recipients": [make_recipient(1)]},
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


@pytest.mark.asyncio
async def test_openapi_documents_assignment_routes(client):
    schema = (await client.get("/openapi.json")).json()
    expected = {
        "/api/v1/jobs": "post",
        "/api/v1/jobs/{job_id}": "get",
        "/api/v1/jobs/{job_id}/recipients": "get",
        "/api/v1/jobs/{job_id}/certificates/download-all": "get",
        "/api/v1/jobs/{job_id}/certificates/{recipient_id}": "get",
        "/api/v1/health": "get",
    }
    for path, method in expected.items():
        operation = schema["paths"][path][method]
        assert operation.get("summary")
        assert operation.get("responses")
    assert {"202", "422", "503"} <= set(schema["paths"]["/api/v1/jobs"]["post"]["responses"])
    assert "404" in schema["paths"]["/api/v1/jobs/{job_id}"]["get"]["responses"]
    assert "422" in schema["paths"]["/api/v1/jobs/{job_id}/recipients"]["get"]["responses"]
    assert "404" in schema["paths"][
        "/api/v1/jobs/{job_id}/certificates/download-all"
    ]["get"]["responses"]
    assert "503" in schema["paths"]["/api/v1/health"]["get"]["responses"]
    assert "examples" in schema["components"]["schemas"]["JobCreateRequest"]
    for schema_name in (
        "JobCreateResponse",
        "JobResponse",
        "JobListResponse",
        "RecipientListResponse",
        "HealthResponse",
    ):
        assert "examples" in schema["components"]["schemas"][schema_name]
    assert "application/pdf" in schema["paths"][
        "/api/v1/jobs/{job_id}/certificates/{recipient_id}"
    ]["get"]["responses"]["200"]["content"]
