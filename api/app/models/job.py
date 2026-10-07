import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIALLY_FAILED = "PARTIALLY_FAILED"
    FAILED = "FAILED"


class ProcessingMode(str, enum.Enum):
    INLINE = "INLINE"
    SANDBOX = "SANDBOX"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status", "status"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_jobs_user_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=JobStatus.PENDING.value)
    processing_mode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    total_recipients: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    valid_recipients: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    invalid_recipients: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    request_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    enqueue_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    container_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
