"""FastAPI entry point. HTTP only: validation, persistence, enqueueing, status and file serving."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import settings
from app.database import engine
from app.services.rate_limit import close_rate_limit_client

logger = logging.getLogger("certificate_api")


async def run_migrations(attempts: int = 5, delay: float = 2.0) -> None:
    """Run `alembic upgrade head` in a subprocess (used from the lifespan handler)."""
    default_ini = Path(__file__).resolve().parents[1] / "alembic" / "alembic.ini"
    ini = Path(os.getenv("ALEMBIC_INI", str(default_ini)))
    if not ini.is_file():
        raise RuntimeError(f"alembic.ini not found at {ini}")

    last_output = ""
    for attempt in range(1, attempts + 1):
        proc = await asyncio.create_subprocess_exec(
            "alembic", "-c", str(ini), "upgrade", "head",
            cwd=str(ini.parent.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await proc.communicate()
        last_output = output.decode(errors="replace")
        if proc.returncode == 0:
            logger.info("Database migrations applied")
            return
        logger.warning("Migration attempt %s/%s failed: %s", attempt, attempts, last_output)
        await asyncio.sleep(delay)
    raise RuntimeError(f"alembic upgrade head failed:\n{last_output}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO)
    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    if settings.RUN_MIGRATIONS:
        await run_migrations()
    cleanup_task = asyncio.create_task(cleanup_certificate_storage())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        try:
            await close_rate_limit_client()
        finally:
            await engine.dispose()


async def cleanup_certificate_storage() -> None:
    from app.services.certificate_storage import cleanup_expired_certificates

    while True:
        try:
            deleted, bytes_freed = await asyncio.to_thread(
                cleanup_expired_certificates,
                settings.STORAGE_PATH,
                settings.CERTIFICATE_TTL_SECONDS,
            )
            if deleted:
                logger.info(
                    "Expired %s certificate PDF(s), freeing %.2f MiB",
                    deleted,
                    bytes_freed / (1024 * 1024),
                )
        except Exception:
            logger.exception("Could not clean expired certificate PDFs")
        await asyncio.sleep(settings.CERTIFICATE_CLEANUP_INTERVAL_SECONDS)


app = FastAPI(
    title="Bulk Certificate Generator API",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "loc": list(error.get("loc", ())),
            "msg": str(error.get("msg", "Invalid request")),
            "type": str(error.get("type", "value_error")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    job_id = request.path_params.get("job_id")
    logger.exception("Unhandled API exception (job_id=%s)", job_id)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    allow_credentials=True,
)
app.include_router(api_router)
