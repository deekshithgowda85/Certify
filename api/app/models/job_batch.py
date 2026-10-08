import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JobBatch(Base):
    __tablename__ = "job_batches"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_job_batches_user_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    request_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
