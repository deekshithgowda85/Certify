"""Recipient schemas + the strict per-recipient validator."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, field_validator

# Stored in the NOT NULL completion_date column when the supplied value is not a parseable date.
PLACEHOLDER_DATE = date(1970, 1, 1)


class RecipientValidated(BaseModel):
    """Strict validation rules applied to every recipient of a POST /jobs request."""

    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    course_name: str = Field(min_length=1, max_length=255)
    completion_date: date

    @field_validator("name", "course_name", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("completion_date")
    @classmethod
    def _not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("completion_date cannot be in the future")
        return value


class RecipientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    status: Literal["PENDING", "SUCCESS", "FAILED"]
    error_message: Optional[str] = None
    certificate_url: Optional[str] = None


class RecipientListResponse(BaseModel):
    job_id: uuid.UUID
    total: int
    page: int
    size: int
    recipients: list[RecipientOut]


def format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "recipient"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)[:2000]


def validate_recipient(raw: Any) -> tuple[Optional[RecipientValidated], Optional[str]]:
    """Return (validated, None) on success or (None, error message) on failure."""
    if not isinstance(raw, dict):
        return None, "recipient must be an object"
    try:
        return RecipientValidated.model_validate(raw), None
    except ValidationError as exc:
        return None, format_validation_error(exc)


def _as_text(value: Any, limit: int = 255) -> str:
    return "" if value is None else str(value).strip()[:limit]


def fallback_recipient_fields(raw: Any) -> dict[str, Any]:
    """Best-effort column values for an *invalid* recipient so it can still be stored as FAILED."""
    raw = raw if isinstance(raw, dict) else {}
    completion: date = PLACEHOLDER_DATE
    candidate = raw.get("completion_date")
    if isinstance(candidate, str):
        try:
            completion = date.fromisoformat(candidate.strip()[:10])
        except ValueError:
            completion = PLACEHOLDER_DATE
    return {
        "name": _as_text(raw.get("name")),
        "email": _as_text(raw.get("email")),
        "course_name": _as_text(raw.get("course_name")),
        "completion_date": completion,
    }
