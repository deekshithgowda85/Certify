import os
import tempfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.v1.job_responses import content_disposition, safe_filename
from app.models import JobBatch
from app.services import batch_service, job_service
from app.services.certificate_storage import CERTIFICATE_STORAGE_LOCK


def merge_pdfs(target: str, sources: list[Path]) -> None:
    from pypdf import PdfWriter

    with CERTIFICATE_STORAGE_LOCK:
        if any(not source.is_file() for source in sources):
            raise FileNotFoundError("A certificate PDF expired before the merge began")
        writer = PdfWriter()
        try:
            for source in sources:
                writer.append(str(source))
            with open(target, "wb") as output:
                writer.write(output)
        finally:
            writer.close()


async def combined_pdf_response(session, batch: JobBatch) -> FileResponse:
    recipients = await batch_service.list_successful_recipients(session, batch)
    sources = [
        path
        for recipient in recipients
        if (path := job_service.resolve_certificate_path(recipient.certificate_path)) is not None
    ]
    if not recipients:
        raise HTTPException(status_code=404, detail="No certificates available for this batch")
    if len(sources) != len(recipients):
        raise HTTPException(
            status_code=410,
            detail="Certificate PDFs expire after 10 minutes. Regenerate this batch to download them again.",
        )

    handle = tempfile.NamedTemporaryFile(prefix="certificates_", suffix=".pdf", delete=False)
    handle.close()
    try:
        await run_in_threadpool(merge_pdfs, handle.name, sources)
    except FileNotFoundError as exc:
        os.remove(handle.name)
        raise HTTPException(
            status_code=410,
            detail="Certificate PDFs expire after 10 minutes. Regenerate this batch to download them again.",
        ) from exc
    except Exception:
        os.remove(handle.name)
        raise
    return FileResponse(
        handle.name,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(
                f"{safe_filename(batch.title, 'job')}_certificates.pdf"
            )
        },
        background=BackgroundTask(os.remove, handle.name),
    )
