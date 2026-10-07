import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.celery_app import celery_app
from app.config import settings
from app.database import engine

router = APIRouter(tags=["health"])


async def check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis() -> bool:
    client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


@router.get("/health")
async def health() -> JSONResponse:
    db_ok = await check_db()
    redis_ok = await check_redis()
    body = {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "db": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "version": settings.APP_VERSION,
    }
    return JSONResponse(body, status_code=200 if (db_ok and redis_ok) else 503)


def _fetch_pool_status() -> dict:
    result = celery_app.send_task(
        "app.tasks.certificate_task.pool_status", queue=settings.CELERY_QUEUE
    )
    return result.get(timeout=5)


@router.get("/pool/status")
async def pool_status() -> JSONResponse:
    """Container pool state; answered by the dispatcher (the API has no Docker access)."""
    try:
        return JSONResponse(await run_in_threadpool(_fetch_pool_status))
    except Exception:
        return JSONResponse({"detail": "Dispatcher did not answer"}, status_code=503)
