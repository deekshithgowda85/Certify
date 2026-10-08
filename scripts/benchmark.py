#!/usr/bin/env python3
"""Measure direct ReportLab rendering through the dispatcher's INLINE renderer."""
from __future__ import annotations

import argparse
import json
import os
import platform
import tempfile
import time
from pathlib import Path

from app.certificate.pdf_builder import generate_pdf


def peak_rss_mib() -> float | None:
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(value / 1024, 2) if platform.system() == "Linux" else round(value / (1024 * 1024), 2)
    except (ImportError, OSError):
        return None


def benchmark(size: int) -> dict[str, int | float]:
    total_bytes = 0
    with tempfile.TemporaryDirectory(prefix="certify-benchmark-") as temp_dir:
        started = time.perf_counter()
        for index in range(size):
            output = Path(temp_dir) / f"{index:06d}.pdf"
            generate_pdf(
                {
                    "name": f"Benchmark Recipient {index:06d}",
                    "course_name": "Bulk Certificate Generator Benchmark",
                    "completion_date": "2026-10-01",
                },
                os.fspath(output),
            )
            total_bytes += output.stat().st_size
        elapsed = time.perf_counter() - started

    return {
        "recipients": size,
        "elapsed_seconds": round(elapsed, 3),
        "certificates_per_second": round(size / elapsed, 2) if elapsed else 0,
        "total_pdf_bytes": total_bytes,
        "average_pdf_bytes": round(total_bytes / size),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes",
        default="10,100,1000,10000",
        help="comma-separated recipient counts (default: 10,100,1000,10000)",
    )
    args = parser.parse_args()
    sizes = [int(value) for value in args.sizes.split(",")]
    if not sizes or any(size < 1 for size in sizes):
        parser.error("sizes must be positive integers")

    results = [benchmark(size) for size in sizes]
    print(
        json.dumps(
            {
                "benchmark": "direct ReportLab rendering via dispatcher INLINE renderer",
                "python": platform.python_version(),
                "platform": platform.platform(),
                "peak_process_rss_mib": peak_rss_mib(),
                "results": results,
                "scope": (
                    "Excludes API, database, Redis, Celery, container startup, "
                    "and PDF merging. Temporary output is deleted after each run."
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
