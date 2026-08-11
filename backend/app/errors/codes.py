# backend/app/errors/codes.py

from __future__ import annotations

from typing import Literal

from app.features.auth.errors import ErrorCode as AuthErrorCode
from app.features.cashout.errors import ErrorCode as CashoutErrorCode
from app.features.users.errors import ErrorCode as UserErrorCode

# Cross-cutting codes raised outside any feature (translators, dependencies,
# the SPA catch-all). Features add specific codes on top; there is no generic
# NOT_FOUND — missing entities use their feature's *_NOT_FOUND code.
type BaseErrorCode = Literal[
    "INTERNAL",
    "BAD_REQUEST",
    "VALIDATION_FAILED",
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "ROUTE_NOT_FOUND",
    "CONFLICT",
    "SERVICE_UNAVAILABLE",
]

type ErrorCode = BaseErrorCode | UserErrorCode | AuthErrorCode | CashoutErrorCode

__all__ = ["BaseErrorCode", "ErrorCode"]
