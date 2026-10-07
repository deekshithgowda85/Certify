from pathlib import Path

import pdfplumber
import pytest

from app.certificate.pdf_builder import generate_pdf

RECIPIENT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Deekshith Gowda",
    "email": "deekshith@example.com",
    "course_name": "Python Bootcamp",
    "completion_date": "2024-10-01",
}


def test_pdf_is_generated(tmp_path):
    out = tmp_path / "cert.pdf"
    generate_pdf(RECIPIENT, str(out))
    assert out.exists()
    assert out.stat().st_size > 5000  # a real PDF, not an empty file
    assert out.read_bytes().startswith(b"%PDF")
    assert not Path(str(out) + ".tmp").exists()


def test_pdf_contains_recipient_name(tmp_path):
    out = tmp_path / "cert.pdf"
    generate_pdf(RECIPIENT, str(out))
    with pdfplumber.open(out) as pdf:
        assert len(pdf.pages) == 1
        page = pdf.pages[0]
        assert page.width == pytest.approx(841.89, abs=0.01)
        assert page.height == pytest.approx(595.28, abs=0.01)
        text = page.extract_text()
    assert "Deekshith Gowda" in text
    assert "Certificate of Completion" in text
    assert "Python Bootcamp" in text
    assert "October 1, 2024" in text
    assert "Aereo Certification Program" in text


def test_very_long_name_still_renders(tmp_path):
    out = tmp_path / "long.pdf"
    generate_pdf({**RECIPIENT, "name": "A" * 200}, str(out))
    assert out.exists()


def test_empty_name_raises_and_leaves_no_file(tmp_path):
    out = tmp_path / "bad.pdf"
    with pytest.raises(ValueError):
        generate_pdf({**RECIPIENT, "name": "  "}, str(out))
    assert not out.exists()
    assert not Path(str(out) + ".tmp").exists()
