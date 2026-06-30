# backend/app/errors/types.py

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import IntEnum, StrEnum
from typing import Any, NotRequired, TypedDict

from fastapi import status

# ================================
# ------------ Codes -------------
# ================================


class ErrorCode(StrEnum):
    SERVER_ERROR = "SERVER_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    UNPROCESSABLE = "UNPROCESSABLE"
    IN_USE = "IN_USE"
    ALREADY_EXISTS = "ALREADY_EXISTS"


class ValidationRule(StrEnum):
    EXTRA_FIELD = "EXTRA_FIELD"
    MISSING_FIELD = "MISSING_FIELD"
    BOOLEAN_TYPE = "BOOLEAN_TYPE"
    STRING_TYPE = "STRING_TYPE"
    INTEGER_TYPE = "INTEGER_TYPE"
    DECIMAL_TYPE = "DECIMAL_TYPE"
    OBJECT_TYPE = "OBJECT_TYPE"
    TOO_SMALL = "TOO_SMALL"
    TOO_LARGE = "TOO_LARGE"
    TOO_SHORT = "TOO_SHORT"
    TOO_LONG = "TOO_LONG"
    INVALID_OPTION = "INVALID_OPTION"
    INVALID_MULTIPLE = "INVALID_MULTIPLE"
    INVALID_VALUE = "INVALID_VALUE"


# ================================
# ------------ Status ------------
# ================================


class ErrorStatus(IntEnum):
    HTTP_500_SERVER_ERROR = status.HTTP_500_INTERNAL_SERVER_ERROR
    HTTP_422_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT
    HTTP_409_CONFLICT = status.HTTP_409_CONFLICT
    HTTP_404_NOT_FOUND = status.HTTP_404_NOT_FOUND
    HTTP_403_FORBIDDEN = status.HTTP_403_FORBIDDEN
    HTTP_401_UNAUTHORIZED = status.HTTP_401_UNAUTHORIZED
    HTTP_400_BAD_REQUEST = status.HTTP_400_BAD_REQUEST


# ================================
# ----------- Context ------------
# ================================


class UnprocessableContext(TypedDict, total=False):
    min_value: int
    max_value: int
    max_length: int
    min_length: int
    multiple_of: int
    allowed_values: list[Any]


# ================================
# ----------- Catalog ------------
# ================================


class CatalogEntry(TypedDict):
    status: ErrorStatus
    message: str
    details: NotRequired[Mapping[ValidationRule, Callable[[UnprocessableContext], str]]]


type ErrorCatalog = Mapping[ErrorCode, CatalogEntry]
