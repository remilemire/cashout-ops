# backend/app/features/auth/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ErrorCatalog

type AuthErrorCode = Literal[
    "INVALID_CREDENTIALS",
    "INVALID_SESSION",
    "INVALID_CSRF_TOKEN",
]

auth_error_catalog: ErrorCatalog[AuthErrorCode] = {
    "INVALID_CREDENTIALS": {
        "kind": "UNAUTHORIZED",
        "message": "Incorrect email or password.",
    },
    "INVALID_SESSION": {
        "kind": "UNAUTHORIZED",
        "message": "Invalid or expired session.",
    },
    "INVALID_CSRF_TOKEN": {"kind": "FORBIDDEN", "message": "Invalid CSRF token."},
}

__all__ = ["AuthErrorCode", "auth_error_catalog"]
