# backend/app/features/auth/email_verification/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ErrorCatalog

type EmailVerificationErrorCode = Literal[
    "VERIFICATION_CODE_INVALID",
    "VERIFICATION_CODE_EXPIRED",
    "VERIFICATION_ALREADY_VERIFIED",
    "EMAIL_NOT_VERIFIED",
]

email_verification_error_catalog: ErrorCatalog[EmailVerificationErrorCode] = {
    "VERIFICATION_CODE_INVALID": {
        "kind": "BAD_REQUEST",
        "message": "That verification code is incorrect.",
    },
    "VERIFICATION_CODE_EXPIRED": {
        "kind": "BAD_REQUEST",
        "message": "That verification code has expired. Request a new one.",
    },
    "VERIFICATION_ALREADY_VERIFIED": {
        "kind": "CONFLICT",
        "message": "This email is already verified.",
    },
    "EMAIL_NOT_VERIFIED": {
        "kind": "FORBIDDEN",
        "message": "Please verify your email address to continue.",
    },
}

__all__ = ["EmailVerificationErrorCode", "email_verification_error_catalog"]
