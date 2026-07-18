# backend/app/errors/__init__.py

from __future__ import annotations

from .domain import (
    AlreadyExistsError,
    AppError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    InUseError,
    InvalidStateError,
    NotFoundError,
    ServerError,
    UnauthorizedError,
    UnprocessableError,
)
from .handlers import init_error_handlers
from .openapi import error_responses
from .types import ErrorCode

__all__ = [
    "AlreadyExistsError",
    "AppError",
    "BadRequestError",
    "ConflictError",
    "ErrorCode",
    "ForbiddenError",
    "InUseError",
    "InvalidStateError",
    "NotFoundError",
    "ServerError",
    "UnauthorizedError",
    "UnprocessableError",
    "error_responses",
    "init_error_handlers",
]
