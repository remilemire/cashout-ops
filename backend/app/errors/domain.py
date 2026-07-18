# backend/app/errors/domain.py

from __future__ import annotations

from abc import ABC

from .catalog import CATALOG
from .schemas import ErrorDetail
from .types import ErrorCode


class AppError(Exception, ABC):
    code: ErrorCode
    message: str

    def __init__(self, message: str | None = None):
        self.message = message or CATALOG[self.code]["message"]

    @property
    def name(self) -> str:
        """Human-readable error name; single-sourced from the catalog."""
        return CATALOG[self.code]["error"]


class ServerError(AppError):
    code = ErrorCode.SERVER_ERROR


class BadRequestError(AppError):
    code = ErrorCode.BAD_REQUEST


class UnauthorizedError(AppError):
    code = ErrorCode.UNAUTHORIZED


class ForbiddenError(AppError):
    code = ErrorCode.FORBIDDEN


class NotFoundError(AppError):
    code = ErrorCode.NOT_FOUND


class ConflictError(AppError):
    """Base for 409 conflicts. Conflicts never carry validation details."""


class AlreadyExistsError(ConflictError):
    code = ErrorCode.ALREADY_EXISTS


class InUseError(ConflictError):
    code = ErrorCode.IN_USE


class InvalidStateError(ConflictError):
    code = ErrorCode.INVALID_STATE


class UnprocessableError(AppError):
    code = ErrorCode.UNPROCESSABLE
    errors: list[ErrorDetail]

    def __init__(
        self, message: str | None = None, *, errors: list[ErrorDetail] | None = None
    ):
        self.errors = errors or []
        super().__init__(message)
