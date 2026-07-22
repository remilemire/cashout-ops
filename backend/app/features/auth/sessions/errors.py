# backend/app/features/auth/sessions/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ErrorCatalog

type SessionErrorCode = Literal["INVALID_SESSION"]

session_error_catalog: ErrorCatalog[SessionErrorCode] = {
    "INVALID_SESSION": {
        "kind": "UNAUTHORIZED",
        "message": "Invalid or expired session.",
    },
}

__all__ = ["SessionErrorCode", "session_error_catalog"]
