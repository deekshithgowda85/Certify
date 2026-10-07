# Dispatcher Service

Celery worker that consumes certificate jobs from Redis, selects inline or isolated rendering, tracks per-recipient progress, and finalizes each job.

## Processing flow

1. Consume the API-published job ID from the `certificates` queue.
2. Load pending recipients and select inline rendering at or below `SANDBOX_THRESHOLD`; larger batches use sandbox containers.
3. Render inline PDFs with the dispatcher ReportLab builder or assign the batch to a warm PDF generator container.
4. Persist each recipient outcome and reconcile the job counters/status so one failed certificate does not block others.
5. Retry transient worker/container failures using Celery's task policy; finalize remaining pending records as failed if retries are exhausted.

The dispatcher mounts the shared `certificate_storage` volume and Docker socket. The latter grants substantial host-level control; run only on a trusted Docker host.

## Configuration

Settings are provided through the root `.env` and Compose environment:

- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`: Redis broker and task result backend.
- `DATABASE_URL`: PostgreSQL connection shared with the API and sandbox.
- `SANDBOX_THRESHOLD`: recipient count boundary for inline versus sandbox execution.
- `SANDBOX_MAX_CONTAINERS`: maximum pool size and worker concurrency.
- `SANDBOX_MIN_IDLE`: warm containers created at startup, capped by the maximum.
- `SANDBOX_SLOT_WAIT_SECONDS`: maximum wait for an available sandbox.
- `SANDBOX_TIMEOUT_SECONDS`: per-container execution bound.
- `SANDBOX_NETWORK`, `SANDBOX_IMAGE`, `SANDBOX_CONTAINER_PREFIX`, and `SANDBOX_VOLUME`: sandbox runtime settings.

After changing pool settings, recreate the worker with `docker compose up -d --build dispatcher`.

## Build and run

From the repository root:

```powershell
docker compose build dispatcher
docker compose up -d dispatcher
docker compose logs -f dispatcher
```

## Tests

Dispatcher integration and rendering tests are in `../tests`. Run `python -m pytest tests/ -q` in the dispatcher container; shared test setup skips API-only files.
