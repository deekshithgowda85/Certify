import json
import logging
import os

from app.config import settings
from app.pool.container_pool import pool
from app.services import job_repository as repo

logger = logging.getLogger(__name__)


def run_sandbox(job_id: str):
    """
    Acquire a warm container from pool.
    Write recipients to input.json on shared volume.
    Execute generate.py inside the container.
    Release container back to pool when done.
    """

    # Write input file to shared volume
    job_dir = f"{settings.STORAGE_PATH}/{job_id}"
    os.makedirs(job_dir, exist_ok=True)

    recipient_data = repo.fetch_pending_recipients(job_id)

    input_file = f"{job_dir}/input.json"
    with open(input_file, "w") as f:
        json.dump(recipient_data, f)

    # Bound queueing so Celery can retry instead of exhausting its soft limit.
    container = None

    try:
        container = pool.acquire(job_id, timeout=settings.SANDBOX_SLOT_WAIT_SECONDS)
        # Store container ID in job record
        repo.update_job_container_id(job_id, container.short_id)

        # Execute generate.py inside the warm container
        exit_code, output = container.exec_run(
            cmd=[
                "timeout",
                str(settings.SANDBOX_TIMEOUT_SECONDS),
                "python",
                "/app/generate.py",
            ],
            environment={
                "JOB_ID": job_id,
                "DATABASE_URL": settings.DATABASE_URL,
                "INPUT_FILE": f"/output/{job_id}/input.json",
                "OUTPUT_DIR": f"/output/{job_id}",
            },
            stream=False,
            demux=False,
        )

        logs = output.decode("utf-8", errors="replace") if output else ""
        logger.info(f"Container logs for job {job_id}:\n{logs}")

        if exit_code not in (0, 1):
            # exit 0 = all success, exit 1 = partial failure
            # anything else = container-level crash
            raise RuntimeError(
                f"Container crashed with exit code {exit_code}. "
                f"Logs: {logs}"
            )

    finally:
        # Always release - even if job failed
        if container is not None:
            pool.release(job_id)

        # Clean up input file
        try:
            os.remove(input_file)
        except Exception:
            pass
