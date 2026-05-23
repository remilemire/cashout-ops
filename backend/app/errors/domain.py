# backend/app/errors/domain.py

from __future__ import annotations

from abc import ABC


class DomainError(Exception, ABC):
    message: str

    def __init__(self, message: str | None = None):
        self.message = message or self.message


class ServerError(DomainError):
    message = "server error"


class BadRequestError(ServerError):
    message = "bad request"


class UnauthenticatedError(ServerError):
    message = "Authentication required."


class ForbiddenError(ServerError):
    message = "forbidden"


class NotFoundError(ServerError):
    message = "not found"


class UnprocessableError(ServerError):
    message = "unprocessable entity"


class ConflictError(ServerError):
    message = "conflict error"
