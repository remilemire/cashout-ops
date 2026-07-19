# backend/app/errors/catalog.py

from __future__ import annotations

from collections.abc import Mapping

from fastapi import status

from app.features.auth.errors import auth_error_catalog
from app.features.cashout.errors import cashout_error_catalog
from app.features.users.errors import user_error_catalog

from .codes import BaseErrorCode, ErrorCode
from .contracts import ErrorCatalog, ErrorKind

base_error_catalog: ErrorCatalog[BaseErrorCode] = {
    "INTERNAL": {"kind": "INTERNAL", "message": "Something went wrong."},
    "BAD_REQUEST": {
        "kind": "BAD_REQUEST",
        "message": "The request could not be processed.",
    },
    "VALIDATION_FAILED": {
        "kind": "VALIDATION",
        "message": "There was a problem with the submission.",
    },
    "UNAUTHENTICATED": {"kind": "UNAUTHORIZED", "message": "Authentication required."},
    "FORBIDDEN": {
        "kind": "FORBIDDEN",
        "message": "You do not have permission to perform this action.",
    },
    "NOT_FOUND": {
        "kind": "NOT_FOUND",
        "message": "The requested resource could not be found.",
    },
    "CONFLICT": {
        "kind": "CONFLICT",
        "message": "The request conflicts with the current state.",
    },
    "SERVICE_UNAVAILABLE": {
        "kind": "SERVICE_UNAVAILABLE",
        "message": "The service is temporarily unavailable.",
    },
}

error_catalog: ErrorCatalog[ErrorCode] = {
    **base_error_catalog,
    **user_error_catalog,
    **auth_error_catalog,
    **cashout_error_catalog,
}

kind_to_status: Mapping[ErrorKind, int] = {
    "BAD_REQUEST": status.HTTP_400_BAD_REQUEST,
    "UNAUTHORIZED": status.HTTP_401_UNAUTHORIZED,
    "FORBIDDEN": status.HTTP_403_FORBIDDEN,
    "NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "CONFLICT": status.HTTP_409_CONFLICT,
    "VALIDATION": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "INTERNAL": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "SERVICE_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
}

__all__ = ["base_error_catalog", "error_catalog", "kind_to_status"]
