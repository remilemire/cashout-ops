# backend/app/core/errors.py

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

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

TCode_co = TypeVar("TCode_co", bound=str, covariant=True, default=str)


@dataclass(frozen=True)
class ErrorDefinition(Generic[TCode_co]):
    code: TCode_co
    kind: ErrorKind
    message: str


type ErrorDefinitionList[TCode: str] = Sequence[ErrorDefinition[TCode]]


type ConstraintCodeMap[TCode: str] = Mapping[str, TCode]

__all__ = ["ErrorKind", "ErrorDefinition", "ErrorDefinitionList", "ConstraintCodeMap"]
