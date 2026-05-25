# backend/app/errors/types.py

from __future__ import annotations

from enum import IntEnum
from typing import Any, Literal, TypedDict

from fastapi import status

# ================================
# ------------ Errors ------------
# ================================


type ErrorType = Literal[
    "server_error",
    "unprocessable",
    "conflict",
    "not_found",
    "unauthenticated",
    "forbidden",
    "bad_request",
]


class ErrorStatus(IntEnum):
    HTTP_500_SERVER_ERROR = status.HTTP_500_INTERNAL_SERVER_ERROR
    HTTP_422_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT
    HTTP_409_CONFLICT = status.HTTP_409_CONFLICT
    HTTP_404_NOT_FOUND = status.HTTP_404_NOT_FOUND
    HTTP_403_FORBIDDEN = status.HTTP_403_FORBIDDEN
    HTTP_401_UNAUTHENTICATED = status.HTTP_401_UNAUTHORIZED
    HTTP_400_BAD_REQUEST = status.HTTP_400_BAD_REQUEST


# ================================
# ----------- Contexts -----------
# ================================


class UnprocessableContext(TypedDict, total=False):
    min_value: int
    max_value: int
    max_length: int
    min_length: int
    multiple_of: int
    allowed_values: list[Any]


# ================================
# ------------ Codes -------------
# ================================


type UnprocessableCode = Literal[
    "extra_field",
    "missing_field",
    "boolean_type",
    "string_type",
    "integer_type",
    "decimal_type",
    "object_type",
    "too_small",
    "too_large",
    "too_long",
    "too_short",
    "invalid_option",
    "invalid_multiple",
    "invalid_value",
]


type ConflictCode = Literal[
    "foreign_key",
    "unique",
    "check",
    "integrity",
]
