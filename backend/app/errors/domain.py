# backend/app/errors/domain.py

from __future__ import annotations

from abc import ABC


class DomainError(Exception, ABC):
    message: str

    def __init__(self, message: str | None = None):
        self.message = message or self.message


class ServiceError(DomainError):
    message = "server error"


class BadRequestError(ServiceError):
    message = "bad request"


class UnauthenticatedError(ServiceError):
    message = "Authentication required."


class ForbiddenError(ServiceError):
    message = "forbidden"


class NotFoundError(ServiceError):
    message = "not found"


class UnprocessableError(ServiceError):
    message = "unprocessable entity"


class ConflictError(ServiceError):
    message = "conflict error"
