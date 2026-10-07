# API Service

FastAPI service for account authentication, bulk-job validation and persistence, status reporting, and secure certificate downloads. The API does not render PDFs; the dispatcher and PDF generator own that work.

## Responsibilities

- Register and authenticate users; issue bearer tokens.
- Accept bulk certificate jobs and validate each recipient independently.
- Persist a job and all recipient rows transactionally before publishing work to Celery.
- Expose job progress and paginated recipient results.
- Serve individual PDFs and disk-built ZIP archives from the configured storage root.
- Check database and Redis broker health.
- Enforce shared Redis-backed request limits.

## Local development

From the repository root, activate the project Python environment and install `api/requirements.txt`. Configure `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `STORAGE_PATH`, and `SECRET_KEY`, then start the service:

```powershell
$env:PYTHONPATH = "api"
uvicorn app.main:app --reload --app-dir api
```

The normal Compose startup runs Alembic migrations automatically. OpenAPI documentation is served at `http://localhost:8000/docs`.

## Routes

- `POST /api/v1/auth/register` and `POST /api/v1/auth/login`: create an account or issue an access token.
- `GET /api/v1/auth/me` and `PATCH /api/v1/auth/me`: read or update the authenticated profile.
- `POST /api/v1/jobs`: submit a batch; invalid recipients are stored as failed when at least one recipient is valid. No-valid-recipient requests return `422`.
- `GET /api/v1/jobs` and `GET /api/v1/jobs/{job_id}`: list owned jobs or read progress.
- `GET /api/v1/jobs/{job_id}/recipients`: paginate results and optionally filter by `PENDING`, `SUCCESS`, or `FAILED`.
- `GET /api/v1/jobs/{job_id}/certificates/download-all`: download successful PDFs as a ZIP.
- `GET /api/v1/jobs/{job_id}/certificates/{recipient_id}`: download one successful PDF.
- `GET /api/v1/health`: report database and Redis health.

All job routes are scoped to the authenticated owner. Stored file paths are resolved inside `STORAGE_PATH`; paths outside that root are rejected.

## Request safety

Default Redis limits are 5 login requests and 5 registrations per minute per direct client IP, and 10 job submissions per minute per authenticated user. The API emits `429` with `Retry-After` and rate-limit headers. Limits are configured by `AUTH_RATE_LIMIT_PER_MINUTE`, `JOB_RATE_LIMIT_PER_MINUTE`, and `RATE_LIMIT_WINDOW_SECONDS`. Redis unavailability fails closed with JSON `503`.

Job creation accepts `Idempotency-Key`. The same key and JSON payload return the original result without enqueuing again; reusing a key with a different payload returns `409`. The key and payload fingerprint are persisted in the jobs table by migration `003_job_idempotency`.

## Database migrations

Migrations live in `../alembic/versions`. Apply them from the repository root:

```powershell
$env:PYTHONPATH = "api"
alembic -c alembic/alembic.ini upgrade head
```

## Tests

See [`../tests/README.md`](../tests/README.md). API tests use a real isolated PostgreSQL test database and mock Celery and Redis interactions.
