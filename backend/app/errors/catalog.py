from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from fastapi import status

from app.core.errors import ErrorKind, ErrorKindMap
from app.features.auth.errors import ErrorCode as AuthErrorCode
from app.features.auth.errors import error_kind_map as auth_error_kind_map
from app.features.cashout.errors import ErrorCode as CashoutErrorCode
from app.features.cashout.errors import (
    error_kind_map as cashout_error_kind_map,
)
from app.features.users.errors import ErrorCode as UserErrorCode
from app.features.users.errors import (
    error_kind_map as user_error_kind_map,
)

# Cross-cutting codes raised outside any feature (translators, dependencies,
# the SPA catch-all). Features add specific codes on top; there is no generic
# NOT_FOUND — missing entities use their feature's *_NOT_FOUND code.
type _BaseErrorCode = Literal[
    "INTERNAL",
    "BAD_REQUEST",
    "VALIDATION_FAILED",
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "ROUTE_NOT_FOUND",
    "CONFLICT",
    "RATE_LIMITED",
    "SERVICE_UNAVAILABLE",
]

type ErrorCode = _BaseErrorCode | UserErrorCode | AuthErrorCode | CashoutErrorCode


error_kind_map: ErrorKindMap[ErrorCode] = {
    "INTERNAL": "INTERNAL",
    "BAD_REQUEST": "BAD_REQUEST",
    "VALIDATION_FAILED": "VALIDATION",
    "UNAUTHENTICATED": "UNAUTHORIZED",
    "FORBIDDEN": "FORBIDDEN",
    "ROUTE_NOT_FOUND": "NOT_FOUND",
    "CONFLICT": "CONFLICT",
    "RATE_LIMITED": "TOO_MANY_REQUESTS",
    "SERVICE_UNAVAILABLE": "SERVICE_UNAVAILABLE",
    **user_error_kind_map,
    **auth_error_kind_map,
    **cashout_error_kind_map,
}

kind_status_map: Mapping[ErrorKind, int] = {
    "BAD_REQUEST": status.HTTP_400_BAD_REQUEST,
    "UNAUTHORIZED": status.HTTP_401_UNAUTHORIZED,
    "FORBIDDEN": status.HTTP_403_FORBIDDEN,
    "NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "CONFLICT": status.HTTP_409_CONFLICT,
    "VALIDATION": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "TOO_MANY_REQUESTS": status.HTTP_429_TOO_MANY_REQUESTS,
    "INTERNAL": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "SERVICE_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
}

__all__ = ["ErrorCode", "error_kind_map", "kind_status_map"]
