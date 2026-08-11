# backend/app/features/auth/email_challenges/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ErrorCatalog

# ONE code covers every failure mode (unknown/expired challenge, bad token, no
# code issued yet, wrong code, code attempts exceeded, already consumed,
# deleted user) so the error shape cannot be used for account enumeration.
type EmailChallengeErrorCode = Literal["EMAIL_CHALLENGE_INVALID"]

email_challenge_error_catalog: ErrorCatalog[EmailChallengeErrorCode] = {
    "EMAIL_CHALLENGE_INVALID": {
        "kind": "UNAUTHORIZED",
        "message": "That sign-in link or code is invalid or has expired.",
    },
}

__all__ = ["EmailChallengeErrorCode", "email_challenge_error_catalog"]
