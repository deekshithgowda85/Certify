"""FastAPI entry point. HTTP only: validation, persistence, enqueueing, status and file serving."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.database import engine

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
    yield
    await engine.dispose()


app = FastAPI(
    title="Bulk Certificate Generator API",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.include_router(api_router)
