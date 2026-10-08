import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings


class JobCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    recipients: list[Any] = Field(min_length=1, max_length=settings.MAX_RECIPIENTS_PER_JOB)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "Python Bootcamp",
                    "recipients": [
                        {
                            "name": "Ada Lovelace",
                            "email": "ada@example.com",
                            "course_name": "Python Bootcamp",
                            "completion_date": "2026-10-07",
                        }
                    ],
                }
            ]
        }
    )


class JobBatchCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    recipients: list[Any] = Field(min_length=1, max_length=100000)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class JobBatchCreateResponse(BaseModel):
    batch_id: uuid.UUID
    status: Literal["PENDING", "FAILED"]
    total_recipients: int
    valid_recipients: int
    invalid_recipients: int
    job_count: int


class JobBatchRegenerateResponse(BaseModel):
    batch_id: uuid.UUID
    status: Literal["PENDING"]
    recipients_to_regenerate: int
    job_count: int


class JobBatchResponse(BaseModel):
    job_id: uuid.UUID
    title: str
    status: Literal["PENDING", "PROCESSING", "COMPLETED", "PARTIALLY_FAILED", "FAILED"]
    total_recipients: int
    processed_count: int
    success_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime


class JobCreateResponse(BaseModel):
    job_id: uuid.UUID
    status: Literal["PENDING"]
    total_recipients: int
    valid_recipients: int
    invalid_recipients: int
    message: str = "Job queued. Mode will be decided by dispatcher."

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "job_id": "d9a22120-8fdb-48c9-9ea7-725393f4d3b2",
                    "status": "PENDING",
                    "total_recipients": 2,
                    "valid_recipients": 1,
                    "invalid_recipients": 1,
                    "message": "Job queued. Mode will be decided by dispatcher.",
                }
            ]
        }
    )


class JobResponse(BaseModel):
    job_id: uuid.UUID
    title: str
    status: Literal["PENDING", "PROCESSING", "COMPLETED", "PARTIALLY_FAILED", "FAILED"]
    processing_mode: Optional[str] = None
    total_recipients: int
    processed_count: int
    success_count: int
    failed_count: int
    container_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "job_id": "d9a22120-8fdb-48c9-9ea7-725393f4d3b2",
                    "title": "Python Bootcamp",
                    "status": "PROCESSING",
                    "processing_mode": "INLINE",
                    "total_recipients": 50,
                    "processed_count": 12,
                    "success_count": 11,
                    "failed_count": 1,
                    "container_id": None,
                    "created_at": "2026-10-07T12:00:00Z",
                    "updated_at": "2026-10-07T12:01:00Z",
                }
            ]
        },
    )


class JobListItem(JobResponse):
    recipient_id: Optional[uuid.UUID] = None


class JobListResponse(BaseModel):
    jobs: list[JobListItem]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "jobs": [
                        {
                            "job_id": "d9a22120-8fdb-48c9-9ea7-725393f4d3b2",
                            "title": "Python Bootcamp",
                            "status": "COMPLETED",
                            "processing_mode": "INLINE",
                            "total_recipients": 1,
                            "processed_count": 1,
                            "success_count": 1,
                            "failed_count": 0,
                            "container_id": None,
                            "created_at": "2026-10-07T12:00:00Z",
                            "updated_at": "2026-10-07T12:01:00Z",
                            "recipient_id": "8f951b0d-7222-47ac-8cc7-d477c88a88f3",
                        }
                    ]
                }
            ]
        }
    )


class HealthResponse(BaseModel):
    status: str
    db: str
    broker: str
    version: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"status": "ok", "db": "ok", "broker": "ok", "version": "1.0.0"}
            ]
        }
    )
