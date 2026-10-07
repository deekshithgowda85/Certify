"""Dispatcher settings (pydantic-settings, configured via environment variables)."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/certificates_db"
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    CELERY_TASK_ALWAYS_EAGER: bool = False
    CELERY_QUEUE: str = "certificates"

    STORAGE_PATH: str = "/app/storage/certificates"

    # Mode switching
    SANDBOX_THRESHOLD: int = 10

    # Sandbox container configuration
    SANDBOX_MIN_IDLE: int = Field(default=2, ge=0)
    SANDBOX_MAX_CONTAINERS: int = Field(default=5, ge=1)
    SANDBOX_IMAGE: str = "bulk-certificate-generator-pdf-generator:latest"
    SANDBOX_CONTAINER_PREFIX: str = "sandbox"
    SANDBOX_VOLUME: str = "bulk-certificate-generator_certificate_storage"
    SANDBOX_NETWORK: str = "certify_default"
    SANDBOX_MEM_LIMIT: str = "256m"
    SANDBOX_CPU_PERIOD: int = 100000
    SANDBOX_CPU_QUOTA: int = 50000  # 0.5 CPU
    SANDBOX_TIMEOUT_SECONDS: int = 300
    # Waiting for a free pool container. After this long Celery retries the task.
    SANDBOX_SLOT_WAIT_SECONDS: int = 120

    # Celery limits: must stay HIGHER than the container timeout
    TASK_SOFT_TIME_LIMIT: int = 600
    TASK_TIME_LIMIT: int = 660

    @property
    def sync_database_url(self) -> str:
        url = self.DATABASE_URL
        for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql://" + url[len(prefix):]
        return url


settings = Settings()
