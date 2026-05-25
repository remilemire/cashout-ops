# backend/app/errors/domain.py

from __future__ import annotations

from abc import ABC

from .schemas import ConflictDetail, UnprocessableDetail
from .types import UnprocessableContext


class DomainError(Exception, ABC):
    message: str

    def __init__(self, message: str | None = None):
        self.message = message or self.message


class ServerError(DomainError):
    message = "server error"


class UnprocessableError(ServerError):
    message = "unprocessable entity"
    details: list[UnprocessableDetail]
    ctx: UnprocessableContext | None

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[UnprocessableDetail] = [],
    ):
        self.details = details
        super().__init__(message)


class ConflictError(ServerError):
    message = "conflict error"
    details: list[ConflictDetail]

    def __init__(
        self, message: str | None = None, *, details: list[ConflictDetail] = []
    ):
        self.details = details
        super().__init__(message)


class NotFoundError(ServerError):
    message = "not found"


class ForbiddenError(ServerError):
    message = "forbidden"


class UnauthenticatedError(ServerError):
    message = "Authentication required."


class BadRequestError(ServerError):
    message = "bad request"
