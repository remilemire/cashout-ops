# backend/app/errors/catalog.py

from __future__ import annotations

from collections.abc import Mapping
from typing import ReadOnly, TypedDict

from fastapi import status

from app.core.errors import ErrorDefinition, ErrorDefinitionList, ErrorKind
from app.features.auth.errors import error_definition_list as auth_error_definition_list
from app.features.cashout.errors import (
    error_definition_list as cashout_error_definition_list,
)
from app.features.users.errors import (
    error_definition_list as user_error_definition_list,
)

from .codes import BaseErrorCode, ErrorCode


class ErrorCatalogEntry(TypedDict):
    kind: ReadOnly[ErrorKind]
    message: ReadOnly[str]


type ErrorCatalog = Mapping[ErrorCode, ErrorCatalogEntry]


_base_error_definition_list: ErrorDefinitionList[BaseErrorCode] = [
    ErrorDefinition(code="INTERNAL", kind="INTERNAL", message="Something went wrong."),
    ErrorDefinition(
        code="BAD_REQUEST",
        kind="BAD_REQUEST",
        message="The request could not be processed.",
    ),
    ErrorDefinition(
        code="VALIDATION_FAILED",
        kind="VALIDATION",
        message="There was a problem with the submission.",
    ),
    ErrorDefinition(
        code="UNAUTHENTICATED", kind="UNAUTHORIZED", message="Authentication required."
    ),
    ErrorDefinition(
        code="FORBIDDEN",
        kind="FORBIDDEN",
        message="You do not have permission to perform this action.",
    ),
    ErrorDefinition(
        code="ROUTE_NOT_FOUND",
        kind="NOT_FOUND",
        message="The requested route does not exist.",
    ),
    ErrorDefinition(
        code="CONFLICT",
        kind="CONFLICT",
        message="The request conflicts with the current state.",
    ),
    ErrorDefinition(
        code="SERVICE_UNAVAILABLE",
        kind="SERVICE_UNAVAILABLE",
        message="The service is temporarily unavailable.",
    ),
]

_error_definition_list: ErrorDefinitionList[ErrorCode] = [
    *_base_error_definition_list,
    *user_error_definition_list,
    *auth_error_definition_list,
    *cashout_error_definition_list,
]

error_catalog: ErrorCatalog = {
    definition.code: {"kind": definition.kind, "message": definition.message}
    for definition in _error_definition_list
}

kind_status_map: Mapping[ErrorKind, int] = {
    "BAD_REQUEST": status.HTTP_400_BAD_REQUEST,
    "UNAUTHORIZED": status.HTTP_401_UNAUTHORIZED,
    "FORBIDDEN": status.HTTP_403_FORBIDDEN,
    "NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "CONFLICT": status.HTTP_409_CONFLICT,
    "VALIDATION": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "INTERNAL": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "SERVICE_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
}

__all__ = ["error_catalog", "kind_status_map"]
