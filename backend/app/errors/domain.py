# backend/app/errors/domain.py

from __future__ import annotations

from abc import ABC

from .catalog import CATALOG
from .schemas import ErrorDetail
from .types import ErrorCode


class DomainError(Exception, ABC):
    code: ErrorCode
    message: str

    def __init__(self, message: str | None = None):
        self.message = message or CATALOG[self.code]["message"]

    @property
    def name(self) -> str:
        """Human-readable error name; single-sourced from the catalog."""
        return CATALOG[self.code]["error"]


class ServerError(DomainError):
    code = ErrorCode.SERVER_ERROR


class BadRequestError(DomainError):
    code = ErrorCode.BAD_REQUEST


class UnauthorizedError(DomainError):
    code = ErrorCode.UNAUTHORIZED


class ForbiddenError(DomainError):
    code = ErrorCode.FORBIDDEN


class NotFoundError(DomainError):
    code = ErrorCode.NOT_FOUND


class ConflictError(DomainError):
    """Base for 409 conflicts. Conflicts never carry validation details."""


class AlreadyExistsError(ConflictError):
    code = ErrorCode.ALREADY_EXISTS


class InUseError(ConflictError):
    code = ErrorCode.IN_USE


class InvalidStateError(ConflictError):
    code = ErrorCode.INVALID_STATE


class UnprocessableError(DomainError):
    code = ErrorCode.UNPROCESSABLE
    errors: list[ErrorDetail]

    def __init__(
        self, message: str | None = None, *, errors: list[ErrorDetail] | None = None
    ):
        self.errors = errors or []
        super().__init__(message)
