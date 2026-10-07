import pytest
from fastapi import HTTPException

from app.services import rate_limit


class CountingRedis:
    def __init__(self):
        self.counts = {}

    async def eval(self, script, number_of_keys, key, window):
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], window]


@pytest.mark.asyncio
async def test_rate_limit_returns_429_and_retry_after(monkeypatch):
    redis = CountingRedis()
    monkeypatch.setattr(rate_limit, "redis_client", redis)
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_WINDOW_SECONDS", 60)

    await rate_limit.enforce_rate_limit("jobs:create", "user-1", limit=1)
    with pytest.raises(HTTPException) as caught:
        await rate_limit.enforce_rate_limit("jobs:create", "user-1", limit=1)

    assert caught.value.status_code == 429
    assert 1 <= int(caught.value.headers["Retry-After"]) <= 60
    assert caught.value.headers["X-RateLimit-Limit"] == "1"
    assert caught.value.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_registration_route_limits_by_client_ip(anonymous_client, monkeypatch):
    monkeypatch.setattr(rate_limit, "redis_client", CountingRedis())
    monkeypatch.setattr(rate_limit.settings, "AUTH_RATE_LIMIT_PER_MINUTE", 1)
    request = {
        "full_name": "Rate Limited",
        "password": "password123",
    }

    first = await anonymous_client.post(
        "/api/v1/auth/register",
        json={**request, "email": "first@example.com"},
    )
    limited = await anonymous_client.post(
        "/api/v1/auth/register",
        json={**request, "email": "second@example.com"},
    )

    assert first.status_code == 201
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]
    assert limited.json()["detail"].startswith("Too many requests.")


@pytest.mark.asyncio
async def test_job_creation_route_limits_by_authenticated_user(client, monkeypatch):
    from helpers import make_recipients

    monkeypatch.setattr(rate_limit, "redis_client", CountingRedis())
    monkeypatch.setattr(rate_limit.settings, "JOB_RATE_LIMIT_PER_MINUTE", 1)
    payload = {"title": "Rate Limited Job", "recipients": make_recipients(1)}

    first = await client.post(
        "/api/v1/jobs",
        json=payload,
        headers={"Idempotency-Key": "job-limit-1"},
    )
    limited = await client.post(
        "/api/v1/jobs",
        json=payload,
        headers={"Idempotency-Key": "job-limit-2"},
    )

    assert first.status_code == 202
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]


@pytest.mark.asyncio
async def test_rate_limit_store_failure_returns_json_503(monkeypatch):
    class UnavailableRedis:
        async def eval(self, script, number_of_keys, key, window):
            from redis.exceptions import ConnectionError

            raise ConnectionError("redis unavailable")

    monkeypatch.setattr(rate_limit, "redis_client", UnavailableRedis())
    with pytest.raises(HTTPException) as caught:
        await rate_limit.enforce_rate_limit("auth:login", "127.0.0.1", limit=5)

    assert caught.value.status_code == 503
    assert caught.value.detail == (
        "Request protection is temporarily unavailable. Please try again shortly."
    )
