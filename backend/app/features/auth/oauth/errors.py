# backend/app/features/auth/oauth/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorDefinition, ErrorDefinitionList

# OAUTH_FLOW_INVALID covers every in-flow failure (unknown/expired/replayed
# flow, state mismatch, issuer-denied callback, failed code exchange or
# ID-token validation) so the error shape reveals nothing about which check
# failed. The other two describe stable facts a user can act on: this
# deployment has no account for the identity, or the issuer is not enabled.
type ErrorCode = Literal[
    "OAUTH_FLOW_INVALID",
    "OAUTH_ACCOUNT_NOT_FOUND",
    "OAUTH_ISSUER_NOT_ENABLED",
]

error_definition_list: ErrorDefinitionList[ErrorCode] = [
    ErrorDefinition(
        code="OAUTH_FLOW_INVALID",
        kind="UNAUTHORIZED",
        message="That sign-in attempt is invalid or has expired. Please try again.",
    ),
    ErrorDefinition(
        code="OAUTH_ACCOUNT_NOT_FOUND",
        kind="FORBIDDEN",
        message=(
            "No account here matches that identity. "
            "Ask an admin to create your account."
        ),
    ),
    ErrorDefinition(
        code="OAUTH_ISSUER_NOT_ENABLED",
        kind="NOT_FOUND",
        message="That sign-in provider is not available.",
    ),
]

__all__ = ["ErrorCode", "error_definition_list"]
