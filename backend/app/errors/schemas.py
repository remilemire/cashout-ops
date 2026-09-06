# backend/app/errors/schemas.py

from __future__ import annotations

from pydantic import Field, JsonValue

from app.core.errors import ErrorKind
from app.core.schemas import BaseOut

from .catalog import ErrorCode
from .validation import ValidationIssue


class ErrorResponseSchema(BaseOut):
    kind: ErrorKind
    code: ErrorCode
    ctx: dict[str, JsonValue] = Field(default_factory=dict)
    issues: list[ValidationIssue] | None = None


__all__ = ["ErrorResponseSchema"]
