from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

type ErrorKind = Literal[
    "BAD_REQUEST",
    "NOT_FOUND",
    "CONFLICT",
    "VALIDATION",
    "FORBIDDEN",
    "UNAUTHORIZED",
    "TOO_MANY_REQUESTS",
    "INTERNAL",
    "SERVICE_UNAVAILABLE",
]

type ErrorKindMap[TCode: str] = Mapping[TCode, ErrorKind]
type ConstraintCodeMap[TCode: str] = Mapping[str, TCode]

__all__ = ["ErrorKind", "ErrorKindMap", "ConstraintCodeMap"]
