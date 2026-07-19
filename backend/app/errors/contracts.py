# backend/app/errors/contracts.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, ReadOnly, TypedDict

type ErrorKind = Literal[
    "BAD_REQUEST",
    "NOT_FOUND",
    "CONFLICT",
    "VALIDATION",
    "FORBIDDEN",
    "UNAUTHORIZED",
    "INTERNAL",
    "SERVICE_UNAVAILABLE",
]


class ErrorCatalogEntry(TypedDict):
    kind: ReadOnly[ErrorKind]
    message: ReadOnly[str]


type ErrorCatalog[ErrorCodeT: str] = Mapping[ErrorCodeT, ErrorCatalogEntry]

type ConstraintToCode[ErrorCodeT: str] = Mapping[str, ErrorCodeT]

__all__ = ["ConstraintToCode", "ErrorCatalog", "ErrorCatalogEntry", "ErrorKind"]
