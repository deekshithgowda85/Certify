"""Lifecycle management for generated and merged certificate PDFs."""
from __future__ import annotations

import threading
import time
from pathlib import Path


CERTIFICATE_STORAGE_LOCK = threading.RLock()


def _delete_expired_pdfs(paths: list[Path], cutoff: float) -> tuple[int, int]:
    deleted = 0
    bytes_freed = 0
    for path in paths:
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if not path.is_file() or stat.st_mtime >= cutoff:
            continue
        path.unlink()
        deleted += 1
        bytes_freed += stat.st_size
    return deleted, bytes_freed


def cleanup_expired_certificates(
    storage_path: str | Path,
    ttl_seconds: int = 600,
    now: float | None = None,
) -> tuple[int, int]:
    cutoff = (time.time() if now is None else now) - ttl_seconds
    storage = Path(storage_path)
    with CERTIFICATE_STORAGE_LOCK:
        stored_paths = list(storage.rglob("*.pdf")) if storage.exists() else []
        stored_deleted, stored_bytes = _delete_expired_pdfs(stored_paths, cutoff)
    return stored_deleted, stored_bytes
