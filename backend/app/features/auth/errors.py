# backend/app/features/auth/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ErrorCatalog

from .email_verification.errors import (
    EmailVerificationErrorCode,
    email_verification_error_catalog,
)
from .sessions.errors import SessionErrorCode, session_error_catalog

# Codes owned directly by auth (login + CSRF). Session and email-verification
# codes live in their subfeatures and are folded in below, so auth exposes a
# single error surface for the whole feature.
type AuthOwnErrorCode = Literal[
    "INVALID_CREDENTIALS",
    "INVALID_CSRF_TOKEN",
]

type AuthErrorCode = AuthOwnErrorCode | SessionErrorCode | EmailVerificationErrorCode

_auth_own_error_catalog: ErrorCatalog[AuthOwnErrorCode] = {
    "INVALID_CREDENTIALS": {
        "kind": "UNAUTHORIZED",
        "message": "Incorrect email or password.",
    },
    "INVALID_CSRF_TOKEN": {"kind": "FORBIDDEN", "message": "Invalid CSRF token."},
}

auth_error_catalog: ErrorCatalog[AuthErrorCode] = {
    **_auth_own_error_catalog,
    **session_error_catalog,
    **email_verification_error_catalog,
}

__all__ = [
    "AuthErrorCode",
    "EmailVerificationErrorCode",
    "SessionErrorCode",
    "auth_error_catalog",
    "email_verification_error_catalog",
    "session_error_catalog",
]
