# backend/app/features/auth/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorDefinition, ErrorDefinitionList

from .email_challenges.errors import (
    ErrorCode as EmailChallengeErrorCode,
)
from .email_challenges.errors import (
    error_definition_list as email_challenge_error_definition_list,
)
from .oauth.errors import ErrorCode as OAuthErrorCode
from .oauth.errors import error_definition_list as oauth_error_definition_list
from .shared.sessions.errors import ErrorCode as SessionErrorCode
from .shared.sessions.errors import (
    error_definition_list as session_error_definition_list,
)

# Codes owned directly by auth (CSRF). Session and email-challenge codes live
# in their subfeatures and are folded in below, so auth exposes a single error
# surface for the whole feature.
type _AuthErrorCode = Literal["INVALID_CSRF_TOKEN"]


_auth_error_definition_list: ErrorDefinitionList[_AuthErrorCode] = [
    ErrorDefinition(
        code="INVALID_CSRF_TOKEN",
        kind="FORBIDDEN",
        message="Your session security check failed. Refresh the page and try again.",
    )
]

type ErrorCode = (
    _AuthErrorCode | SessionErrorCode | EmailChallengeErrorCode | OAuthErrorCode
)

error_definition_list: ErrorDefinitionList[ErrorCode] = [
    *_auth_error_definition_list,
    *session_error_definition_list,
    *email_challenge_error_definition_list,
    *oauth_error_definition_list,
]

__all__ = [
    "ErrorCode",
    "error_definition_list",
]
