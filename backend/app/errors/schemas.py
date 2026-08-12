# backend/app/errors/schemas.py

from __future__ import annotations

from app.core.errors import ErrorKind
from app.core.schemas import BaseOut

from .catalog import ErrorCode
from .validation import ValidationIssueCode


class ValidationIssueSchema(BaseOut):
    code: ValidationIssueCode
    path: list[str | int]
    message: str


class ErrorResponseSchema(BaseOut):
    kind: ErrorKind
    code: ErrorCode
    message: str
    issues: list[ValidationIssueSchema] | None = None


__all__ = ["ErrorResponseSchema", "ValidationIssueSchema"]
