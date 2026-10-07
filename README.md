# Bulk Certificate Generator

A production-style API that turns a list of recipients into PDF certificates.
Small jobs are rendered **inline** inside the Celery worker; large jobs get their own
**ephemeral Docker container (sandbox)** that renders the PDFs in isolation and removes itself.

Stack: FastAPI · Celery · Redis 7 · PostgreSQL 15 · SQLAlchemy 2 · Alembic · ReportLab · Docker SDK.

## Architecture Overview

```
                         HTTP
   client  ───────────────────────────►  ┌──────────────────────┐
                                         │  api  (FastAPI :8000)│  validation, DB writes,
   GET status / certificates / zip  ◄──  │  no PDF logic        │  status + file serving
                                         └───────┬───────▲──────┘
                              INSERT job +       │       │ SELECT status
                              recipients         ▼       │
                                         ┌──────────────────────┐
                                         │  db  (PostgreSQL 15) │◄──────────────┐
                                         └──────────────────────┘               │ status updates
                                                                                │ (per recipient commit)
        send_task(job_id)                ┌──────────────────────┐               │
   api ───────────────────────────────►  │  redis 7 (broker)    │               │
                                         └──────────┬───────────┘               │
                                                    │ queue "certificates"      │
                                                    ▼                           │
                                         ┌──────────────────────────────────────┴───┐
                                         │ dispatcher  (Celery worker – the brain)  │
                                         │  count PENDING recipients                │
                                         │  <= SANDBOX_THRESHOLD ?                  │
                                         └───────┬──────────────────────┬───────────┘
                                   MODE 1 INLINE │                      │ MODE 2 SANDBOX
                                  (<= 10 people) │                      │ (> 10 people)
                                                 ▼                      ▼
                                   ┌───────────────────────┐   acquire pool container (cap = 5)
                                   │ ReportLab in-process  │            │
                                   │ pdf_builder.py        │            ▼
                                   └──────────┬────────────┘   docker.sock ─► host Docker daemon
                                              │                          │ spawns sibling container
                                              │                          ▼
                                              │             ┌────────────────────────────────┐
                                              │             │ pdf-generator (ephemeral)      │
                                              │             │ python:3.11-slim + ReportLab   │
                                              │             │ 256 MB / 0.5 CPU, removed after│
                                              │             │ reads input.json, writes PDFs, │
                                              │             │ updates PostgreSQL itself      │
                                              │             └───────────────┬────────────────┘
                                              ▼                             ▼
                              ┌────────────────────────────────────────────────────────┐
                              │ named volume  certificate_storage                      │
                              │ api & dispatcher: /app/storage/certificates            │
                              │ pdf-generator:    /output                              │
                              └────────────────────────────────────────────────────────┘
```

| Service         | Role                                                                                                                       |
| --------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `api`           | HTTP only. Validates input, stores job + recipients, enqueues the Celery task, serves status and files.                    |
| `dispatcher`    | Celery worker. Chooses INLINE or SANDBOX, spawns/monitors containers, finalizes job status. Mounts `/var/run/docker.sock`. |
| `redis`         | Celery broker and result backend.                                                                                          |
| `db`            | PostgreSQL: `jobs` and `recipients`.                                                                                       |
| `pdf-generator` | Image only (never a running service). Built by `docker compose build`, spawned on demand.                                  |

## How Threshold Switching Works

The dispatcher counts the job's `PENDING` recipients and compares with `SANDBOX_THRESHOLD` (default `10`):

- **8 recipients (<= 10) → INLINE.** PDFs are rendered inside the worker process: no container start-up cost.
- **10 recipients → INLINE**, **11 recipients → SANDBOX** (the boundary is inclusive).
- **50 recipients (> 10) → SANDBOX.** The dispatcher writes `input.json` onto the shared volume, takes a
  sandbox slot, starts an isolated `pdf-generator` container (256 MB RAM, 0.5 CPU), waits for it (max 300 s),
  reads its exit code/logs, reconciles the database and removes the container.

Recipients that were invalid at request time are stored as `FAILED` immediately and never count towards the threshold.

**Concurrency cap.** The dispatcher uses one Celery process with five worker threads and one shared pool. The pool
never creates more than five containers, including its two warm idle containers. A job waits up to
`SANDBOX_SLOT_WAIT_SECONDS` (120 s) for a container; after that, the task retries through Celery instead of waiting
until the 600-second soft limit. Each container execution is independently capped at 300 seconds.

## Scalability

- The bundled deployment intentionally runs one dispatcher process. Scaling dispatcher replicas would create one
  five-container pool per replica and is not supported while the cap is process-local.
- Each sandbox: 256 MB RAM, 0.5 CPU, 64 PIDs, all Linux capabilities dropped, `no-new-privileges`.

**Capacity estimate.** Up to five jobs can execute concurrently because the dispatcher has five threads. The
practical active generation limit is five jobs, matching the pool's hard ceiling of five containers.
Additional API requests are accepted and queued by Celery/Redis. Actual throughput depends on recipient count,
PDF generation time, database latency, and host CPU; with sandbox jobs, a rough upper bound is
`5 / average sandbox duration` jobs per second.

## Quick Start

```bash
git clone <repo> && cd bulk-certificate-generator
cp .env.example .env
docker compose build
docker compose up -d
# API:  http://localhost:8000
# Docs: http://localhost:8000/docs
```

The API applies Alembic migrations on start-up (`alembic upgrade head`, run from the FastAPI lifespan).
`docker compose build` also builds the `bulk-certificate-generator-pdf-generator:latest` image, and the dispatcher
waits for that build step to complete before it starts.

## Running Tests

The API and the dispatcher are separate services that both have a top-level `app` package, so each suite runs in
its own container. Files that belong to the other service are skipped automatically, so the same command works in both:

```bash
docker compose exec api        python -m pytest tests/ -v --tb=short   # API + validation tests
docker compose exec dispatcher python -m pytest tests/ -v --tb=short   # inline, sandbox, threshold, PDF tests
```

Tests use a separate `certificates_test` database (created automatically), a temporary storage directory, Celery
eager mode, `fakeredis` and a mocked Docker client - no real containers are started.

## API Examples (curl)

```bash
# Create a job (202). Invalid recipients are stored as FAILED; 422 if none are valid.
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Python Bootcamp 2024",
    "recipients": [
      {"name": "Deekshith Gowda", "email": "deekshith@example.com",
       "course_name": "Python Bootcamp", "completion_date": "2024-10-01"},
      {"name": "Bad Email", "email": "nope", "course_name": "Python Bootcamp", "completion_date": "2024-10-01"}
    ]
  }'

JOB=<job_id from the response>

# Job status (mode, counters, container id)
curl -s http://localhost:8000/api/v1/jobs/$JOB

# Recipients: filter + paginate
curl -s "http://localhost:8000/api/v1/jobs/$JOB/recipients?status=FAILED&page=1&size=20"

# One certificate (PDF download)
curl -OJ http://localhost:8000/api/v1/jobs/$JOB/certificates/<recipient_id>

# All successful certificates as a ZIP
curl -OJ http://localhost:8000/api/v1/jobs/$JOB/certificates/download-all

# Health (DB + Redis)
curl -s http://localhost:8000/api/v1/health
```

Job statuses: `PENDING → PROCESSING → COMPLETED | PARTIALLY_FAILED | FAILED`.

## Design Decisions

1. **Why ephemeral containers for large jobs?** Isolation and resource control. A big or misbehaving job is
   capped at 256 MB / 0.5 CPU and cannot starve the worker or other jobs; the container disappears afterwards, so
   nothing leaks between jobs. Containers are siblings on the host Docker daemon (via the socket), not Docker-in-Docker.
2. **Why a semaphore (queueing) over hard rejection?** Bursts are normal. Queueing keeps every accepted job
   alive and smooths load; clients already poll job status. The cap is a Redis-backed counter so it holds across
   Celery's prefork processes and scaled-out dispatchers.
3. **Why inline for small jobs?** Starting a container costs seconds; rendering ten PDFs costs milliseconds.
4. **Why per-recipient DB commit?** Progress is visible immediately, a crash loses at most one recipient, one bad
   recipient cannot roll back the others, and a retried task only processes what is still `PENDING`.
5. **Why a separate dispatcher service from the api?** The API stays a thin, fast HTTP layer. Only the
   dispatcher needs the Docker socket (a privileged capability), and it can be scaled independently.

### Notes on deviations from a literal reading of the spec

- **Certificate paths** are stored relative to the storage root (`<job_id>/<recipient_id>.pdf`). The container sees the volume
  at `/output`, the api at `/app/storage/certificates`, so an absolute path would only be valid in one of them.
- **Container exit codes:** `generate.py` exits `1` when _some_ recipients failed (their rows are already updated).
  The dispatcher therefore does not treat a non-zero exit as an exception; it marks anything still `PENDING` as
  `FAILED`, recomputes counters from the `recipients` table and sets the final job status. Docker daemon/image errors
  _are_ raised so Celery retries (3 times, then the job is failed).
- **`api` build context is the repo root** (`api/Dockerfile`) so the image can include `./alembic`.
- **Date validation** compares with the server (UTC) date: "not in the future" means after today in UTC.
- PDFs use the built-in Helvetica fonts, which cover Latin text. Names in other scripts need an embedded TTF
  font (they fail per-recipient with an error message rather than breaking the batch).
- **Security:** mounting `docker.sock` gives the dispatcher root-equivalent control of the host. Run it on a trusted
  host, and consider a docker-socket-proxy in production.

## Future Improvements

- Flower dashboard for Celery monitoring
- WebSocket endpoint for real-time progress
- S3/MinIO for certificate storage instead of a local volume
- Kubernetes HPA for dispatcher auto-scaling (and Kubernetes Jobs instead of the Docker socket)
