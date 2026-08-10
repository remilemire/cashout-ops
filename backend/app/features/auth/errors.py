# backend/app/features/auth/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ErrorCatalog

from .login_challenges.errors import (
    LoginChallengeErrorCode,
    login_challenge_error_catalog,
)
from .sessions.errors import SessionErrorCode, session_error_catalog

# Codes owned directly by auth (CSRF). Session and login-challenge codes live
# in their subfeatures and are folded in below, so auth exposes a single error
# surface for the whole feature.
type AuthOwnErrorCode = Literal["INVALID_CSRF_TOKEN"]

type AuthErrorCode = AuthOwnErrorCode | SessionErrorCode | LoginChallengeErrorCode

_auth_own_error_catalog: ErrorCatalog[AuthOwnErrorCode] = {
    "INVALID_CSRF_TOKEN": {
        "kind": "FORBIDDEN",
        "message": "Your session security check failed. Refresh the page and try again.",
    },
}

auth_error_catalog: ErrorCatalog[AuthErrorCode] = {
    **_auth_own_error_catalog,
    **session_error_catalog,
    **login_challenge_error_catalog,
}

__all__ = [
    "AuthErrorCode",
    "SessionErrorCode",
    "LoginChallengeErrorCode",
    "auth_error_catalog",
    "session_error_catalog",
    "login_challenge_error_catalog",
]
