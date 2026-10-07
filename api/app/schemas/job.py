import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings


class JobCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    # Recipients are validated one by one in the service layer so that a single bad
    # recipient never rejects the whole request (it is stored as FAILED instead).
    recipients: list[dict[str, Any]] = Field(min_length=1, max_length=settings.MAX_RECIPIENTS_PER_JOB)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class JobCreateResponse(BaseModel):
    job_id: uuid.UUID
    recipient_id: uuid.UUID
    status: str
    total_recipients: int
    valid_recipients: int
    invalid_recipients: int
    processing_mode: Optional[str] = None
    message: str = "Job queued. Mode will be decided by dispatcher."


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    title: str
    status: str
    processing_mode: Optional[str] = None
    total_recipients: int
    processed_count: int
    success_count: int
    failed_count: int
    container_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    recipient_id: Optional[uuid.UUID] = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
    version: str
