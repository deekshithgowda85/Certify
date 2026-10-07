import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.orm import Session


@pytest.mark.asyncio
async def test_admin_metrics_includes_live_queue_and_database_aggregates(
    client, monkeypatch, sync_engine
):
    from app.api.v1 import metrics
    from app.models import Job, Recipient

    now = datetime.now(timezone.utc)
    completed_job_id = uuid.uuid4()
    failed_job_id = uuid.uuid4()
    processing_job_id = uuid.uuid4()

    with Session(sync_engine) as session:
        session.add_all(
            [
                Job(
                    id=completed_job_id,
                    title="Completed",
                    status="COMPLETED",
                    processing_mode="INLINE",
                    total_recipients=1,
                    processed_count=1,
                    success_count=1,
                    failed_count=0,
                    created_at=now,
                    updated_at=now,
                ),
                Job(
                    id=failed_job_id,
                    title="Failed",
                    status="FAILED",
                    processing_mode="SANDBOX",
                    total_recipients=1,
                    processed_count=1,
                    success_count=0,
                    failed_count=1,
                    created_at=now,
                    updated_at=now,
                ),
                Job(
                    id=processing_job_id,
                    title="Processing",
                    status="PROCESSING",
                    total_recipients=1,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.add_all(
            [
                Recipient(
                    job_id=completed_job_id,
                    name="Completed User",
                    email="completed@example.com",
                    course_name="Python",
                    completion_date=date.today(),
                    status="SUCCESS",
                    created_at=now,
                    updated_at=now,
                ),
                Recipient(
                    job_id=failed_job_id,
                    name="Failed User",
                    email="failed@example.com",
                    course_name="Python",
                    completion_date=date.today(),
                    status="FAILED",
                    error_message="PDF generation failed",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()

    async def queue_depth():
        return 3

    monkeypatch.setattr(metrics, "_get_queue_depth", queue_depth)
    monkeypatch.setattr(
        metrics,
        "_fetch_pool_status",
        lambda: {
            "idle": 1,
            "busy": 1,
            "min_idle": 1,
            "max_total": 8,
            "busy_jobs": {str(processing_job_id): "worker-1"},
            "containers": [
                {
                    "id": "worker-1",
                    "name": "sandbox-1",
                    "role": "busy",
                    "status": "running",
                    "health": "healthy",
                    "cpu_percent": 37.0,
                    "mem_used_mb": 102.0,
                    "mem_limit_mb": 256.0,
                    "uptime_seconds": 125.0,
                }
            ],
        },
    )

    response = await client.get("/api/v1/admin/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["queue"] == {
        "name": body["queue"]["name"],
        "pending": 3,
        "processing": 1,
        "completed_24h": 1,
        "failed_24h": 1,
        "status": "busy",
    }
    assert body["services"] == {
        "api": "ok",
        "db": "ok",
        "redis": "ok",
        "dispatcher": "ok",
    }
    assert body["sandboxes"]["active"] == 1
    assert body["sandboxes"]["idle"] == 1
    assert body["sandboxes"]["capacity"] == 8
    assert len(body["sandboxes"]["slots"]) == 8
    assert body["containers"][0]["id"] == "worker-1"
    assert body["containers"][0]["cpu_percent"] == 37.0
    assert body["containers"][0]["mem_used_mb"] == 102.0
    assert body["containers"][0]["mem_limit_mb"] == 256.0
    assert body["containers"][0]["uptime_seconds"] == 125.0
    assert body["containers"][0]["job_id"] == str(processing_job_id)
    assert body["containers"][0]["job_progress"] == {"processed": 0, "total": 1}
    assert body["sandboxes"]["slots"][0]["job_id"] == str(processing_job_id)
    assert body["sandboxes"]["slots"][0]["job_progress"] == {"processed": 0, "total": 1}
    assert sum(point["inline"] + point["sandbox"] for point in body["throughput"]) == 1
    assert body["failures"] == [{"message": "PDF generation failed", "count": 1}]
    assert len(body["events"]) == 3
