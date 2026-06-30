# backend/app/errors/schemas.py

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.base import BaseOut

from .catalog import VALIDATION_DETAILS
from .types import ErrorCode, ErrorStatus, UnprocessableContext, ValidationRule

# ================================
# ------------ Details -----------
# ================================


class ErrorDetail(BaseOut):
    rule: ValidationRule
    detail: str
    path: list[str | int]

    @classmethod
    def build(
        cls,
        rule: ValidationRule,
        *,
        path: list[str | int],
        ctx: UnprocessableContext | None = None,
        detail: str | None = None,
    ) -> ErrorDetail:
        # The catalog message for the rule is only a fallback: an explicitly
        # provided `detail` always wins; `ctx` feeds contextual messages.
        return cls(
            rule=rule,
            detail=detail or VALIDATION_DETAILS[rule](ctx or {}),
            path=path,
        )


# ================================
# ------------- Body -------------
# ================================


class ErrorBody(BaseOut):
    error: str
    code: ErrorCode
    message: str
    errors: list[ErrorDetail] | None = None


# ================================
# ----------- Response -----------
# ================================


@dataclass(frozen=True)
class ErrorResponse:
    status: ErrorStatus
    body: ErrorBody
