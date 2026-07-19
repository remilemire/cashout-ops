# backend/app/errors/validation/error.py

from __future__ import annotations

from collections.abc import Sequence
from typing import NotRequired, ReadOnly, TypedDict

from ..app_error import AppError
from .issues import ValidationIssueCode, ValidationIssueContext


class ValidationIssueData(TypedDict):
    code: ReadOnly[ValidationIssueCode]
    path: ReadOnly[Sequence[str | int]]
    ctx: NotRequired[ReadOnly[ValidationIssueContext]]


class ValidationError(AppError):
    """VALIDATION_FAILED with per-field issues; messages come from the issue
    catalog when the response is formatted."""

    issues: Sequence[ValidationIssueData]

    def __init__(
        self,
        issues: Sequence[ValidationIssueData],
        message: str | None = None,
    ):
        super().__init__("VALIDATION_FAILED", message)
        self.issues = issues


__all__ = ["ValidationError", "ValidationIssueData"]
