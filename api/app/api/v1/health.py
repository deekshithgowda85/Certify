import logging

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.celery_app import celery_app
from app.config import settings
from app.database import engine
from app.schemas.job import HealthResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger("certificate_api")


async def check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return False


def _check_broker_connection() -> bool:
    connection = None
    try:
        connection = celery_app.connection_for_write()
        connection.ensure_connection(max_retries=0, timeout=2)
        return True
    except Exception as exc:
        logger.warning("Broker health check failed: %s", exc)
        return False
    finally:
        if connection is not None:
            try:
                connection.release()
            except Exception:
                logger.debug("Could not release broker health-check connection", exc_info=True)


async def check_broker() -> bool:
    return await run_in_threadpool(_check_broker_connection)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check database and message broker health",
    responses={
        503: {
            "description": "One or more dependencies are unavailable",
            "content": {
                "application/json": {
                    "example": {"status": "degraded", "db": "ok", "broker": "error", "version": "1.0.0"}
                }
            },
        }
    },
)
async def health() -> JSONResponse:
    db_ok = await check_db()
    broker_ok = await check_broker()
    body = {
        "status": "ok" if (db_ok and broker_ok) else "degraded",
        "db": "ok" if db_ok else "error",
        "broker": "ok" if broker_ok else "error",
        "version": settings.APP_VERSION,
    }
    return JSONResponse(body, status_code=200 if (db_ok and broker_ok) else 503)


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
