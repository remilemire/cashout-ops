from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field, JsonValue

from app.core.schemas import BaseOut

from .app_error import AppError


class ValidationIssue(BaseOut):
    """Pydantic's error type, API field path, and safe constraint context."""

    code: str
    path: list[str | int]
    ctx: dict[str, JsonValue] = Field(default_factory=dict)


class ValidationError(AppError):
    def __init__(self, issues: Sequence[ValidationIssue]):
        super().__init__("VALIDATION_FAILED")
        self.issues = list(issues)


__all__ = ["ValidationError", "ValidationIssue"]
