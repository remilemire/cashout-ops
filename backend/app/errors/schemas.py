# backend/app/errors/schemas.py

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.base import BaseOut

from .types import ErrorCode, ErrorStatus, ValidationRule

# ================================
# ------------ Details -----------
# ================================


class ErrorDetail(BaseOut):
    rule: ValidationRule
    detail: str
    path: list[str | int]


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
