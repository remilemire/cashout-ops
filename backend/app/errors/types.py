# backend/app/errors/types.py

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Any, NotRequired, TypedDict

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
    INVALID_STATE = "INVALID_STATE"


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
    error: str
    status: int
    message: str
    details: NotRequired[Mapping[ValidationRule, Callable[[UnprocessableContext], str]]]


type ErrorCatalog = Mapping[ErrorCode, CatalogEntry]
