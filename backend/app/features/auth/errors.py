# backend/app/features/auth/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ErrorCatalog

from .email_verification.errors import (
    EmailVerificationErrorCode,
    email_verification_error_catalog,
)
from .login_challenges.errors import (
    LoginChallengeErrorCode,
    login_challenge_error_catalog,
)
from .sessions.errors import SessionErrorCode, session_error_catalog

# Codes owned directly by auth (CSRF). Session, email-verification, and
# login-challenge codes live in their subfeatures and are folded in below, so
# auth exposes a single error surface for the whole feature.
type AuthOwnErrorCode = Literal["INVALID_CSRF_TOKEN"]

type AuthErrorCode = (
    AuthOwnErrorCode
    | SessionErrorCode
    | EmailVerificationErrorCode
    | LoginChallengeErrorCode
)

_auth_own_error_catalog: ErrorCatalog[AuthOwnErrorCode] = {
    "INVALID_CSRF_TOKEN": {"kind": "FORBIDDEN", "message": "Invalid CSRF token."},
}

auth_error_catalog: ErrorCatalog[AuthErrorCode] = {
    **_auth_own_error_catalog,
    **session_error_catalog,
    **email_verification_error_catalog,
    **login_challenge_error_catalog,
}

__all__ = [
    "AuthErrorCode",
    "EmailVerificationErrorCode",
    "SessionErrorCode",
    "LoginChallengeErrorCode",
    "auth_error_catalog",
    "email_verification_error_catalog",
    "session_error_catalog",
    "login_challenge_error_catalog",
]
