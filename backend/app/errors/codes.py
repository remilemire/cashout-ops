# backend/app/errors/codes.py

from __future__ import annotations

from typing import Literal

from app.features.auth.errors import AuthErrorCode
from app.features.cashout.errors import CashoutErrorCode
from app.features.email_verification.errors import EmailVerificationErrorCode
from app.features.invitations.errors import InvitationErrorCode
from app.features.users.errors import UserErrorCode

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

type ErrorCode = (
    BaseErrorCode
    | UserErrorCode
    | AuthErrorCode
    | InvitationErrorCode
    | EmailVerificationErrorCode
    | CashoutErrorCode
)

__all__ = ["BaseErrorCode", "ErrorCode"]
