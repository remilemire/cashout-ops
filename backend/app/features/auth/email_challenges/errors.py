# backend/app/features/auth/email_challenges/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorDefinition, ErrorDefinitionList

# ONE code covers every failure mode (unknown/expired challenge, bad token, no
# code issued yet, wrong code, code attempts exceeded, already consumed,
# deleted user) so the error shape cannot be used for account enumeration.
type ErrorCode = Literal["EMAIL_CHALLENGE_INVALID"]

error_definition_list: ErrorDefinitionList[ErrorCode] = [
    ErrorDefinition(
        code="EMAIL_CHALLENGE_INVALID",
        kind="UNAUTHORIZED",
        message="That sign-in link or code is invalid or has expired.",
    )
]

__all__ = ["ErrorCode", "error_definition_list"]
