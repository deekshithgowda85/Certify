"""MODE 1 — INLINE: generate the PDFs inside the Celery worker process (no container overhead)."""
from __future__ import annotations

import logging
from pathlib import Path

from app.certificate.pdf_builder import generate_pdf
from app.config import settings
from app.services import job_repository as repo

logger = logging.getLogger(__name__)


def run_inline(job_id: str) -> dict[str, int]:
    """Generate certificates for every PENDING recipient of the job.

    Each recipient is isolated (try/except) and committed on its own, so progress
    is visible to the API immediately and one failure never affects the others.
    """
    job_dir = Path(settings.STORAGE_PATH) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    succeeded = failed = 0
    for recipient in repo.fetch_pending_recipients(job_id):
        recipient_id = recipient["id"]
        output_path = job_dir / f"{recipient_id}.pdf"
        try:
            generate_pdf(recipient, str(output_path))
            repo.record_success(job_id, recipient_id, f"{job_id}/{recipient_id}.pdf")
            succeeded += 1
        except Exception as exc:
            logger.exception("Certificate generation failed for recipient %s", recipient_id)
            repo.record_failure(job_id, recipient_id, str(exc) or exc.__class__.__name__)
            failed += 1

    repo.finalize_job(job_id)
    return {"succeeded": succeeded, "failed": failed}
