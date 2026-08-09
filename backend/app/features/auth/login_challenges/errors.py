# backend/app/features/auth/login_challenges/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ErrorCatalog

# ONE code covers every failure mode (unknown/expired challenge, bad token, no
# code issued yet, wrong code, attempts exceeded, already consumed, deleted
# user) so the error shape cannot be used for account enumeration.
type LoginChallengeErrorCode = Literal["LOGIN_CHALLENGE_INVALID"]

login_challenge_error_catalog: ErrorCatalog[LoginChallengeErrorCode] = {
    "LOGIN_CHALLENGE_INVALID": {
        "kind": "UNAUTHORIZED",
        "message": "This sign-in request is invalid or has expired. "
        "Return to the login page and try again.",
    },
}

__all__ = ["LoginChallengeErrorCode", "login_challenge_error_catalog"]
