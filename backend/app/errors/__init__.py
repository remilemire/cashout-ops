# backend/app/errors/__init__.py

from __future__ import annotations

from .domain import (
    AlreadyExistsError,
    BadRequestError,
    ConflictError,
    DomainError,
    ForbiddenError,
    InUseError,
    NotFoundError,
    ServerError,
    UnauthenticatedError,
    UnprocessableError,
)
from .handlers import init_error_handlers
from .openapi import ERROR_RESPONSES

__all__ = [
    "AlreadyExistsError",
    "BadRequestError",
    "ConflictError",
    "DomainError",
    "ForbiddenError",
    "InUseError",
    "NotFoundError",
    "ServerError",
    "UnauthenticatedError",
    "UnprocessableError",
    "init_error_handlers",
    "ERROR_RESPONSES",
]
