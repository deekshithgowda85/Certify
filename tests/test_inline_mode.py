from pathlib import Path

from app.services import inline_generator
from app.services.inline_generator import run_inline


def test_inline_generates_pdfs(create_job, get_job, get_recipients, storage_path):
    job_id = create_job(3)
    summary = run_inline(job_id)

    assert summary == {"succeeded": 3, "failed": 0}
    recipients = get_recipients(job_id)
    assert all(r.status == "SUCCESS" for r in recipients)
    for r in recipients:
        pdf = Path(storage_path) / job_id / f"{r.id}.pdf"
        assert pdf.exists() and pdf.stat().st_size > 0
        assert r.certificate_path == f"{job_id}/{r.id}.pdf"

    job = get_job(job_id)
    assert job.status == "COMPLETED"
    assert (job.processed_count, job.success_count, job.failed_count) == (3, 3, 0)


def test_inline_partial_failure(create_job, get_job, get_recipients, monkeypatch):
    real_generate = inline_generator.generate_pdf

    def flaky(recipient, output_path):
        if recipient["name"] == "Learner 1":
            raise RuntimeError("boom")
        return real_generate(recipient, output_path)

    monkeypatch.setattr(inline_generator, "generate_pdf", flaky)

    job_id = create_job(3)
    summary = run_inline(job_id)
    assert summary == {"succeeded": 2, "failed": 1}

    by_name = {r.name: r for r in get_recipients(job_id)}
    assert by_name["Learner 1"].status == "FAILED"
    assert "boom" in by_name["Learner 1"].error_message
    assert by_name["Learner 0"].status == "SUCCESS"
    assert by_name["Learner 2"].status == "SUCCESS"

    job = get_job(job_id)
    assert job.status == "PARTIALLY_FAILED"
    assert (job.processed_count, job.success_count, job.failed_count) == (3, 2, 1)


def test_inline_all_failed_marks_job_failed(create_job, get_job, monkeypatch):
    def always_fail(recipient, output_path):
        raise RuntimeError("nope")

    monkeypatch.setattr(inline_generator, "generate_pdf", always_fail)
    job_id = create_job(2)
    run_inline(job_id)
    assert get_job(job_id).status == "FAILED"
