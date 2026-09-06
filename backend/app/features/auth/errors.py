# backend/app/features/auth/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorKindMap

from .email_challenges.errors import (
    ErrorCode as EmailChallengeErrorCode,
)
from .email_challenges.errors import (
    error_kind_map as email_challenge_error_kind_map,
)
from .oauth.errors import ErrorCode as OAuthErrorCode
from .oauth.errors import error_kind_map as oauth_error_kind_map
from .sessions.errors import ErrorCode as SessionErrorCode
from .sessions.errors import (
    error_kind_map as session_error_kind_map,
)

# Codes owned directly by auth (CSRF). Session and email-challenge codes live
# in their subfeatures and are folded in below, so auth exposes a single error
# surface for the whole feature.
type _AuthErrorCode = Literal["INVALID_CSRF_TOKEN"]


_auth_error_kind_map: ErrorKindMap[_AuthErrorCode] = {
    "INVALID_CSRF_TOKEN": "FORBIDDEN",
}

type ErrorCode = (
    _AuthErrorCode | SessionErrorCode | EmailChallengeErrorCode | OAuthErrorCode
)

error_kind_map: ErrorKindMap[ErrorCode] = {
    **_auth_error_kind_map,
    **session_error_kind_map,
    **email_challenge_error_kind_map,
    **oauth_error_kind_map,
}

__all__ = [
    "ErrorCode",
    "error_kind_map",
]
