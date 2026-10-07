#!/usr/bin/env python3
"""
Ephemeral PDF generator. Run inside the sandbox Docker container.

Reads recipients from the INPUT_FILE env var (JSON list).
Writes PDFs to the OUTPUT_DIR env var.
Updates recipient/job status in PostgreSQL directly.
Exits 0 on full success, 1 if any generation failed.

STANDALONE: no FastAPI, no Celery. Only ReportLab + psycopg2.
"""
from __future__ import annotations

import math
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)  # (841.89, 595.28) points
CENTER_X = PAGE_WIDTH / 2

DARK_BLUE = colors.Color(0, 0, 0.5)
GOLD = colors.Color(1, 0.84, 0)
TEXT_GRAY = colors.Color(0.3, 0.3, 0.3)
DATE_GRAY = colors.Color(0.4, 0.4, 0.4)
FOOTER_GRAY = colors.Color(0.5, 0.5, 0.5)

MAX_TEXT_WIDTH = PAGE_WIDTH - 140


def _format_date(value: Any) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        value = date.fromisoformat(str(value)[:10])
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def _fit_text(pdf: canvas.Canvas, text: str, font: str, size: float, min_size: float = 10) -> tuple[str, float]:
    """Shrink the font (and finally truncate with an ellipsis) so the text fits the page."""
    while size > min_size and pdf.stringWidth(text, font, size) > MAX_TEXT_WIDTH:
        size -= 1
    if pdf.stringWidth(text, font, size) > MAX_TEXT_WIDTH:
        while len(text) > 1 and pdf.stringWidth(text + "...", font, size) > MAX_TEXT_WIDTH:
            text = text[:-1]
        text = text.rstrip() + "..."
    return text, size


def _centered(pdf: canvas.Canvas, text: str, y: float, font: str, size: float, color) -> None:
    text, size = _fit_text(pdf, text, font, size)
    pdf.setFillColor(color)
    pdf.setFont(font, size)
    pdf.drawCentredString(CENTER_X, y, text)


def _draw_borders(pdf: canvas.Canvas) -> None:
    pdf.setStrokeColor(DARK_BLUE)
    pdf.setLineWidth(3)
    pdf.rect(20, 20, 801.89, 555.28)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1)
    pdf.rect(25, 25, 791.89, 545.28)


def _draw_corner_ornaments(pdf: canvas.Canvas) -> None:
    inset = 38
    corners = [
        (inset, inset, 0),
        (PAGE_WIDTH - inset, inset, 90),
        (PAGE_WIDTH - inset, PAGE_HEIGHT - inset, 180),
        (inset, PAGE_HEIGHT - inset, 270),
    ]
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.2)
    for cx, cy, start in corners:
        for radius in (10, 18, 26):
            pdf.arc(cx - radius, cy - radius, cx + radius, cy + radius, start, 90)


def _draw_seal(pdf: canvas.Canvas, cx: float, cy: float) -> None:
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(2)
    pdf.circle(cx, cy, 38)
    pdf.setStrokeColor(DARK_BLUE)
    pdf.setLineWidth(1)
    pdf.circle(cx, cy, 30)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.2)
    for step in range(36):
        angle = math.radians(step * 10)
        pdf.line(
            cx + 32 * math.cos(angle), cy + 32 * math.sin(angle),
            cx + 36.5 * math.cos(angle), cy + 36.5 * math.sin(angle),
        )
    pdf.setFillColor(DARK_BLUE)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(cx, cy + 2, "CERTIFIED")
    pdf.setFont("Helvetica", 6)
    pdf.drawCentredString(cx, cy - 7, "AUTHENTIC")


def _render(pdf: canvas.Canvas, recipient: Mapping[str, Any]) -> None:
    name = str(recipient["name"]).strip()
    course = str(recipient["course_name"]).strip()
    if not name:
        raise ValueError("recipient name is empty")
    if not course:
        raise ValueError("course name is empty")
    completed_on = _format_date(recipient["completion_date"])

    _draw_borders(pdf)
    _draw_corner_ornaments(pdf)

    # 3. Title
    _centered(pdf, "Certificate of Completion", 480, "Helvetica-Bold", 40, DARK_BLUE)
    # 4. Decorative line under the title
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(2)
    pdf.line(CENTER_X - 150, 462, CENTER_X + 150, 462)
    # 5-8. Body
    _centered(pdf, "This certifies that", 420, "Helvetica", 16, TEXT_GRAY)
    _centered(pdf, name, 370, "Helvetica-Bold", 32, DARK_BLUE)
    _centered(pdf, "has successfully completed", 330, "Helvetica", 16, TEXT_GRAY)
    _centered(pdf, course, 285, "Helvetica-Bold", 24, colors.black)
    # 9. Date
    _centered(pdf, f"Completed on: {completed_on}", 200, "Helvetica-Oblique", 14, DATE_GRAY)
    # 10. Bottom line
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.5)
    pdf.line(CENTER_X - 200, 120, CENTER_X + 200, 120)
    # 11. Footer
    _centered(pdf, "Aereo Certification Program", 105, "Helvetica", 10, FOOTER_GRAY)

    # Signature line (left) and seal (right)
    pdf.setStrokeColor(FOOTER_GRAY)
    pdf.setLineWidth(0.8)
    pdf.line(80, 120, 200, 120)
    pdf.setFillColor(FOOTER_GRAY)
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(140, 106, "Authorized Signature")
    _draw_seal(pdf, 700, 122)


def generate_pdf(recipient: Mapping[str, Any], output_path: str) -> None:
    """Render an A4-landscape certificate for `recipient` and write it atomically to `output_path`.

    `recipient` needs the keys: name, course_name, completion_date (ISO string or date).
    Raises on any problem; the file is only visible once it has been written completely.
    """
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    try:
        pdf = canvas.Canvas(str(temp), pagesize=landscape(A4), pageCompression=0)
        pdf.setTitle(f"Certificate - {str(recipient['name']).strip()}")
        pdf.setAuthor("Aereo Certification Program")
        pdf.setSubject(f"Certificate of Completion: {str(recipient['course_name']).strip()}")
        pdf.setCreator("Bulk Certificate Generator")
        _render(pdf, recipient)
        pdf.showPage()
        pdf.save()
        os.replace(temp, target)
    except Exception:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


# ----------------------------------------------------------------------------------
# Container entry point
# ----------------------------------------------------------------------------------
import json
import sys

import psycopg2


def _normalize_dsn(url: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


DATABASE_URL = _normalize_dsn(os.environ["DATABASE_URL"])
JOB_ID = os.environ["JOB_ID"]
INPUT_FILE = os.environ["INPUT_FILE"]
OUTPUT_DIR = os.environ["OUTPUT_DIR"]


def get_db():
    return psycopg2.connect(DATABASE_URL)


def main() -> int:
    with open(INPUT_FILE, encoding="utf-8") as handle:
        recipients = json.load(handle)

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    conn = get_db()
    cur = conn.cursor()
    has_failure = False

    for recipient in recipients:
        recipient_id = recipient["id"]
        output_path = f"{OUTPUT_DIR}/{recipient_id}.pdf"
        # The API serves files relative to its storage root, which is the parent of OUTPUT_DIR.
        relative_path = f"{JOB_ID}/{recipient_id}.pdf"

        try:
            generate_pdf(recipient, output_path)

            cur.execute(
                """
                UPDATE recipients
                SET status='SUCCESS', certificate_path=%s, error_message=NULL, updated_at=NOW()
                WHERE id=%s AND status='PENDING'
                """,
                (relative_path, recipient_id),
            )
            if cur.rowcount:
                cur.execute(
                    """
                    UPDATE jobs
                    SET success_count = success_count + 1,
                        processed_count = processed_count + 1,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (JOB_ID,),
                )
            conn.commit()
            print(f"[OK] {recipient['name']} -> {output_path}", flush=True)

        except Exception as exc:  # failure isolation: one bad recipient never stops the batch
            has_failure = True
            conn.rollback()
            cur.execute(
                """
                UPDATE recipients
                SET status='FAILED', error_message=%s, updated_at=NOW()
                WHERE id=%s AND status='PENDING'
                """,
                (str(exc)[:1000], recipient_id),
            )
            if cur.rowcount:
                cur.execute(
                    """
                    UPDATE jobs
                    SET failed_count = failed_count + 1,
                        processed_count = processed_count + 1,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (JOB_ID,),
                )
            conn.commit()
            print(f"[FAIL] {recipient.get('name')}: {exc}", file=sys.stderr, flush=True)

    cur.close()
    conn.close()
    return 1 if has_failure else 0


if __name__ == "__main__":
    sys.exit(main())
