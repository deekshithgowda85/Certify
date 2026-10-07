import pytest

from app.config import settings
from app.tasks.certificate_task import certificate_task, decide_mode


def test_decide_mode_pure_function():
    assert decide_mode(0, 10) == "INLINE"
    assert decide_mode(10, 10) == "INLINE"
    assert decide_mode(11, 10) == "SANDBOX"


def test_inline_mode_selected_for_small_job(create_job, get_job, storage_path):
    job_id = create_job(5)  # below threshold (10)
    certificate_task.apply(args=[job_id], throw=True)  # eager execution

    job = get_job(job_id)
    assert job.processing_mode == "INLINE"
    assert job.status == "COMPLETED"
    assert job.container_id is None


def test_sandbox_mode_selected_for_large_job(create_job, get_job, mock_docker):
    job_id = create_job(15)  # above threshold (10)
    certificate_task.apply(args=[job_id], throw=True)

    job = get_job(job_id)
    assert job.processing_mode == "SANDBOX"
    assert mock_docker.client.containers.run.call_count == 2
    assert job.container_id == "abc123def456"


@pytest.mark.parametrize(
    "count, expected_mode",
    [(10, "INLINE"), (11, "SANDBOX")],
)
def test_threshold_boundary(create_job, get_job, mock_docker, count, expected_mode):
    assert settings.SANDBOX_THRESHOLD == 10
    job_id = create_job(count)
    certificate_task.apply(args=[job_id], throw=True)

    assert get_job(job_id).processing_mode == expected_mode
    if expected_mode == "SANDBOX":
        assert mock_docker.client.containers.run.call_count == 2
    else:
        mock_docker.client.containers.run.assert_not_called()


def test_threshold_is_configurable(create_job, get_job, monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_THRESHOLD", 2)
    job_id = create_job(2)
    certificate_task.apply(args=[job_id], throw=True)
    assert get_job(job_id).processing_mode == "INLINE"


def test_only_pending_recipients_count_towards_threshold(create_job, get_job, get_recipients, sync_engine):
    """Recipients already FAILED at creation time (invalid input) must not push a job into SANDBOX mode."""
    from sqlalchemy import text

    job_id = create_job(15)
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE recipients SET status='FAILED', error_message='invalid' WHERE id IN "
                "(SELECT id FROM recipients WHERE job_id = :j ORDER BY name LIMIT 6)"
            ),
            {"j": job_id},
        )
    certificate_task.apply(args=[job_id], throw=True)  # 9 pending -> INLINE
    job = get_job(job_id)
    assert job.processing_mode == "INLINE"
    assert job.status == "PARTIALLY_FAILED"
