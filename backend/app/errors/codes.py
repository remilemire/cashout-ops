# backend/app/errors/codes.py

from __future__ import annotations

from typing import Literal

from app.features.auth.errors import AuthErrorCode
from app.features.cashout.errors import CashoutErrorCode
from app.features.users.errors import UserErrorCode

# Cross-cutting codes raised outside any feature (translators, dependencies,
# Entity.get_active, the SPA catch-all). Features add specific codes on top.
type BaseErrorCode = Literal[
    "INTERNAL",
    "BAD_REQUEST",
    "VALIDATION_FAILED",
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "NOT_FOUND",
    "CONFLICT",
    "SERVICE_UNAVAILABLE",
]

type ErrorCode = BaseErrorCode | UserErrorCode | AuthErrorCode | CashoutErrorCode

__all__ = ["BaseErrorCode", "ErrorCode"]
