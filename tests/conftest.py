"""Shared pytest configuration.

The API and the dispatcher are separate services that both expose a top-level `app`
package, so each suite runs inside its own container:

    docker compose exec api        python -m pytest tests/ -v --tb=short
    docker compose exec dispatcher python -m pytest tests/ -v --tb=short

Test files that belong to the other service are skipped automatically.
"""
import importlib.util
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def _prepare_environment() -> None:
    """Point the app at a separate test database BEFORE any `app.*` module is imported."""
    base = make_url(os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@db:5432/certificates_db"))
    test_db = os.environ.get("TEST_DB_NAME", "certificates_test")

    admin = create_engine(base.set(drivername="postgresql", database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": test_db}).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{test_db}"'))
    admin.dispose()

    os.environ["DATABASE_URL"] = base.set(drivername="postgresql", database=test_db).render_as_string(
        hide_password=False
    )
    os.environ["TESTING"] = "1"
    os.environ["STORAGE_PATH"] = tempfile.mkdtemp(prefix="certs_test_")
    os.environ["SANDBOX_THRESHOLD"] = "10"
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "True"
    os.environ["RUN_MIGRATIONS"] = "0"


_prepare_environment()

HAS_API = importlib.util.find_spec("app.main") is not None
HAS_DISPATCHER = importlib.util.find_spec("app.tasks") is not None

collect_ignore = []
if not HAS_API:
    collect_ignore += ["test_api_jobs.py", "test_api_metrics.py", "test_auth.py", "test_validation.py"]
if not HAS_DISPATCHER:
    collect_ignore += [
        "test_inline_mode.py",
        "test_threshold_switching.py",
        "test_certificate_pdf.py",
        "test_container_pool.py",
    ]


# --------------------------------------------------------------------------- common
@pytest.fixture(scope="session")
def sync_engine():
    from app.database import Base
    import app.models  # noqa: F401

    engine = create_engine(os.environ["DATABASE_URL"])
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_db(sync_engine):
    with sync_engine.begin() as conn:
        existing_tables = set(inspect(conn).get_table_names())
        tables = [name for name in ("recipients", "jobs", "users") if name in existing_tables]
        if tables:
            conn.execute(text(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def storage_path():
    return os.environ["STORAGE_PATH"]


# --------------------------------------------------------------------------- API side
if HAS_API:
    import httpx
    import pytest_asyncio

    @pytest.fixture(autouse=True)
    def enqueue_mock(monkeypatch):
        """Never talk to a real broker from API tests."""
        from app.services import job_service

        mock = MagicMock(name="enqueue_certificate_task")
        monkeypatch.setattr(job_service, "enqueue_certificate_task", mock)
        return mock

    @pytest.fixture(autouse=True)
    def rate_limit_mock(monkeypatch):
        """Keep ordinary API tests independent of Redis while exercising the real routes."""
        from app.services import rate_limit

        class UnlimitedRedis:
            async def eval(self, script, number_of_keys, key, window):
                return [1, window]

            async def aclose(self):
                return None

        monkeypatch.setattr(rate_limit, "redis_client", UnlimitedRedis())

    @pytest_asyncio.fixture
    async def client():
        from app.main import app

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            response = await http_client.post(
                "/api/v1/auth/register",
                json={
                    "full_name": "Test Owner",
                    "email": "test-owner@example.com",
                    "password": "password123",
                },
            )
            http_client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
            yield http_client

    @pytest_asyncio.fixture
    async def anonymous_client():
        from app.main import app

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client

    @pytest_asyncio.fixture
    async def create_job(client):
        """create_job(recipients, title=...) -> httpx.Response of POST /api/v1/jobs."""

        async def _create(recipients, title="Test Job"):
            return await client.post("/api/v1/jobs", json={"title": title, "recipients": recipients})

        return _create


# --------------------------------------------------------------------------- dispatcher side
if HAS_DISPATCHER:
    import uuid
    from datetime import date, timedelta

    @pytest.fixture
    def create_job(sync_engine):
        """create_job(n_recipients, title=...) -> job_id (str); inserts PENDING rows directly."""
        from app.models import Job, Recipient

        def _create(count: int, title: str = "Test Job") -> str:
            job_id = uuid.uuid4()
            with Session(sync_engine) as session:
                session.add(Job(id=job_id, title=title, status="PENDING", total_recipients=count))
                session.flush()
                for i in range(count):
                    session.add(
                        Recipient(
                            job_id=job_id,
                            name=f"Learner {i}",
                            email=f"learner{i}@example.com",
                            course_name="Python Bootcamp",
                            completion_date=date.today() - timedelta(days=1),
                            status="PENDING",
                        )
                    )
                session.commit()
            return str(job_id)

        return _create

    @pytest.fixture(autouse=True)
    def reset_container_pool():
        """Keep the lazy Docker client and pool isolated between dispatcher tests."""
        from app.pool import container_pool

        container_pool.pool.shutdown()
        container_pool.pool._pool = None
        container_pool.client._client = None
        yield
        container_pool.pool.shutdown()
        container_pool.pool._pool = None
        container_pool.client._client = None

    @pytest.fixture
    def get_job(sync_engine):
        from app.models import Job

        def _get(job_id: str):
            with Session(sync_engine) as session:
                return session.get(Job, uuid.UUID(job_id))

        return _get

    @pytest.fixture
    def get_recipients(sync_engine):
        from sqlalchemy import select
        from app.models import Recipient

        def _get(job_id: str):
            with Session(sync_engine) as session:
                return list(
                    session.execute(
                        select(Recipient).where(Recipient.job_id == uuid.UUID(job_id)).order_by(Recipient.name)
                    ).scalars()
                )

        return _get

    @pytest.fixture
    def mock_docker():
        """Replace docker.from_env() with a fake client whose container exits 0."""
        with patch("docker.from_env") as from_env:
            client = MagicMock(name="docker_client")
            container = MagicMock(name="container")
            container.short_id = "abc123def456"
            container.wait.return_value = {"StatusCode": 0}
            container.logs.return_value = b"[OK] generated"
            container.exec_run.return_value = (0, b"[OK] generated")
            client.containers.run.return_value = container
            from_env.return_value = client
            yield SimpleNamespace(from_env=from_env, client=client, container=container)
