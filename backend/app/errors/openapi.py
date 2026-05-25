# backend/app/errors/openapi.py

from __future__ import annotations

from .schemas import (
    BadRequestResponse,
    ConflictResponse,
    ErrorResponse,
    ForbiddenResponse,
    NotFoundResponse,
    ServerErrorResponse,
    UnauthenticatedResponse,
    UnprocessableResponse,
)
from .types import ErrorStatus

ERROR_RESPONSES: dict[int, dict[str, type[ErrorResponse]]] = {
    ErrorStatus.HTTP_400_BAD_REQUEST.value: {"model": BadRequestResponse},
    ErrorStatus.HTTP_401_UNAUTHENTICATED.value: {"model": UnauthenticatedResponse},
    ErrorStatus.HTTP_403_FORBIDDEN.value: {"model": ForbiddenResponse},
    ErrorStatus.HTTP_404_NOT_FOUND.value: {"model": NotFoundResponse},
    ErrorStatus.HTTP_409_CONFLICT.value: {"model": ConflictResponse},
    ErrorStatus.HTTP_422_UNPROCESSABLE.value: {"model": UnprocessableResponse},
    ErrorStatus.HTTP_500_SERVER_ERROR.value: {"model": ServerErrorResponse},
}
