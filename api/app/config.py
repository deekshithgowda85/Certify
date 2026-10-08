"""Application settings (pydantic-settings, configured via environment variables)."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/certificates_db"
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    CELERY_TASK_ALWAYS_EAGER: bool = False

    STORAGE_PATH: str = "/app/storage/certificates"
    CERTIFICATE_TTL_SECONDS: int = Field(default=600, ge=60)
    CERTIFICATE_CLEANUP_INTERVAL_SECONDS: int = Field(default=60, ge=10)

    SANDBOX_THRESHOLD: int = 10

    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    TESTING: bool = False
    RUN_MIGRATIONS: bool = True
    MAX_RECIPIENTS_PER_JOB: int = 10000
    AUTH_RATE_LIMIT_PER_MINUTE: int = Field(default=5, ge=1)
    JOB_RATE_LIMIT_PER_MINUTE: int = Field(default=10, ge=1)
    PUBLIC_JOB_RATE_LIMIT_PER_MINUTE: int = Field(default=3, ge=1)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1)
    SANDBOX_MAX_CONTAINERS: int = 5
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"

    # Name of the Celery task implemented by the dispatcher service.
    CERTIFICATE_TASK_NAME: str = "app.tasks.certificate_task.certificate_task"
    CELERY_QUEUE: str = "certificates"

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL
        for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url[len(prefix):]
        return url


settings = Settings()
