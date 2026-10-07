"""Redis-backed fixed-window rate limiting shared across API workers."""
import logging
import time

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger("certificate_api")
redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)

_INCREMENT_WITH_EXPIRY = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


def client_ip(request: Request) -> str:
    """Use the direct peer address; forwarded headers are not trusted by default."""
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(scope: str, identity: str, limit: int) -> None:
    window = settings.RATE_LIMIT_WINDOW_SECONDS
    now = time.time()
    bucket = int(now // window)
    window_ttl = window - int(now) % window
    key = f"certify:rate-limit:{scope}:{identity}:{bucket}"
    try:
        count, ttl = await redis_client.eval(_INCREMENT_WITH_EXPIRY, 1, key, window_ttl)
    except (RedisError, TimeoutError) as exc:
        logger.exception("Rate-limit storage unavailable for scope=%s", scope)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Request protection is temporarily unavailable. Please try again shortly.",
        ) from exc

    remaining = max(0, limit - int(count))
    reset_at = int(now) + max(1, int(ttl))
    headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(reset_at),
    }
    if int(count) > limit:
        retry_after = max(1, int(ttl))
        headers["Retry-After"] = str(retry_after)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Try again in {retry_after} seconds.",
            headers=headers,
        )


async def close_rate_limit_client() -> None:
    await redis_client.aclose()
