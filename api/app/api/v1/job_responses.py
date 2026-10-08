import re
import zipfile
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from app.models import Job
from app.schemas.job import JobListItem

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t\x00]+')


def safe_filename(value: str, fallback: str = "certificate") -> str:
    cleaned = _UNSAFE_FILENAME.sub("_", value).strip(" ._")
    return cleaned or fallback


def content_disposition(filename: str) -> str:
    fallback = filename.encode("ascii", "ignore").decode().replace('"', "") or "download"
    return f"attachment; filename=\"{fallback}\"; filename*=utf-8''{quote(filename)}"


def job_response(job: Job, recipient_id: Optional[uuid.UUID] = None) -> JobListItem:
    return JobListItem(
        job_id=job.id,
        title=job.title,
        status=job.status,
        processing_mode=job.processing_mode,
        total_recipients=job.total_recipients,
        processed_count=job.processed_count,
        success_count=job.success_count,
        failed_count=job.failed_count,
        container_id=job.container_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        recipient_id=recipient_id,
    )


def build_zip(target: str, entries: list[tuple[Path, str]]) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for path, arcname in entries:
            archive.write(path, arcname=arcname)
