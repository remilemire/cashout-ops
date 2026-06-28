# backend/app/errors/domain.py

from __future__ import annotations

from abc import ABC

from .catalog import CATALOG
from .schemas import ErrorDetail
from .types import ErrorCode


class DomainError(Exception, ABC):
    code: ErrorCode
    name: str
    message: str

    def __init__(self, message: str | None = None):
        self.message = message or CATALOG[self.code]["message"]


class ServerError(DomainError):
    code = ErrorCode.SERVER_ERROR
    name = "Server Error"


class BadRequestError(DomainError):
    code = ErrorCode.BAD_REQUEST
    name = "Bad Request"


class UnauthenticatedError(DomainError):
    code = ErrorCode.UNAUTHENTICATED
    name = "Unauthenticated"


class ForbiddenError(DomainError):
    code = ErrorCode.FORBIDDEN
    name = "Forbidden"


class NotFoundError(DomainError):
    code = ErrorCode.NOT_FOUND
    name = "Not Found"


class ConflictError(DomainError):
    """Base for 409 conflicts. Conflicts never carry validation details."""


class AlreadyExistsError(ConflictError):
    code = ErrorCode.ALREADY_EXISTS
    name = "Already Exists"


class InUseError(ConflictError):
    code = ErrorCode.IN_USE
    name = "In Use"


class UnprocessableError(DomainError):
    code = ErrorCode.UNPROCESSABLE
    name = "Unprocessable Entity"
    errors: list[ErrorDetail]

    def __init__(
        self, message: str | None = None, *, errors: list[ErrorDetail] | None = None
    ):
        self.errors = errors or []
        super().__init__(message)
