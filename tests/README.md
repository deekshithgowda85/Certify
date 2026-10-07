# Test Suite

The test suite covers API contract and authentication, recipient validation, job progress and downloads, Redis rate limits, inline rendering, sandbox behavior, and PDF output.

## Compose (recommended)

Run the API tests against the API's isolated PostgreSQL test database and with its broker mocked:

```powershell
docker compose exec -T api python -m pytest tests/test_api_jobs.py tests/test_auth.py tests/test_validation.py tests/test_api_metrics.py tests/test_rate_limit.py -q
```

Run worker/PDF tests inside the dispatcher image:

```powershell
docker compose exec -T dispatcher python -m pytest tests/test_inline_mode.py tests/test_threshold_switching.py tests/test_certificate_pdf.py tests/test_container_pool.py -q
```

## Fixtures and isolation

`conftest.py` creates/uses a separate `certificates_test` database (override with `TEST_DB_NAME`), prepares schema for tests, truncates test records between cases, and assigns temporary certificate storage. API fixtures replace enqueue and rate-limit storage calls so test requests do not publish work or consume shared limits. Dispatcher fixtures isolate the pool and mock Docker when a real engine is not required.

Do not point `DATABASE_URL` or `TEST_DB_NAME` at production data: test setup creates and truncates a separate database.

## Local run

The API suite requires reachable PostgreSQL and uses the environment's API dependencies. From the repository root, set `PYTHONPATH=api`, configure `DATABASE_URL`, then run:

```powershell
python -m pytest tests/test_api_jobs.py tests/test_auth.py tests/test_validation.py tests/test_api_metrics.py tests/test_rate_limit.py -q
```
