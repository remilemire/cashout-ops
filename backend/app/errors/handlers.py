# backend/app/errors/handlers.py

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .catalog import CATALOG
from .domain import (
    AlreadyExistsError,
    BadRequestError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ServerError,
    UnauthenticatedError,
    UnprocessableError,
)
from .schemas import ErrorBody, ErrorResponse
from .translators import translate_integrity_error, translate_validation_error
from .types import ErrorStatus


def init_error_handlers(app: FastAPI) -> None:

    # ================================
    # ------------ Domain ------------
    # ================================

    @app.exception_handler(DomainError)
    def handle_domain_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: DomainError
    ) -> JSONResponse:
        return format_error_response(build_response(exc))

    # ================================
    # ----------- Pydantic -----------
    # ================================

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    def handle_validation_error(  # type: ignore[reportUnusedFunction]
        request: Request,
        exc: ValidationError | RequestValidationError,
    ) -> JSONResponse:
        error = UnprocessableError(errors=translate_validation_error(exc))
        return format_error_response(build_response(error))

    # ================================
    # ---------- SQLAlchemy ----------
    # ================================

    @app.exception_handler(IntegrityError)
    def handle_integrity_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        return format_error_response(build_response(translate_integrity_error(exc)))

    # ================================
    # ---------- Starlette -----------
    # ================================

    @app.exception_handler(StarletteHTTPException)
    def handle_http_exception(  # type: ignore[reportUnusedFunction]
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return format_error_response(build_response(_http_error(exc.status_code)))

    # ================================
    # ----------- Uncaught -----------
    # ================================

    @app.exception_handler(Exception)
    def handle_uncaught_exception(  # type: ignore[reportUnusedFunction]
        request: Request, exc: Exception
    ) -> JSONResponse:
        return format_error_response(build_response(ServerError()))


# ================================
# ----------- Helpers ------------
# ================================


STATUS_TO_ERROR: Mapping[int, type[DomainError]] = {
    ErrorStatus.HTTP_400_BAD_REQUEST.value: BadRequestError,
    ErrorStatus.HTTP_401_UNAUTHENTICATED.value: UnauthenticatedError,
    ErrorStatus.HTTP_403_FORBIDDEN.value: ForbiddenError,
    ErrorStatus.HTTP_404_NOT_FOUND.value: NotFoundError,
    ErrorStatus.HTTP_409_CONFLICT.value: AlreadyExistsError,
    ErrorStatus.HTTP_422_UNPROCESSABLE.value: UnprocessableError,
    ErrorStatus.HTTP_500_SERVER_ERROR.value: ServerError,
}


def _http_error(status_code: int) -> DomainError:
    factory = STATUS_TO_ERROR.get(status_code)
    if factory is not None:
        return factory()
    return BadRequestError() if 400 <= status_code < 500 else ServerError()


def build_response(exc: DomainError) -> ErrorResponse:
    entry = CATALOG[exc.code]
    errors = exc.errors if isinstance(exc, UnprocessableError) else None
    return ErrorResponse(
        status=entry["status"],
        body=ErrorBody(
            error=exc.name,
            code=exc.code,
            message=exc.message,
            errors=errors or None,
        ),
    )


def format_error_response(response: ErrorResponse) -> JSONResponse:
    return JSONResponse(
        status_code=response.status.value,
        content=response.body.to_response(),
    )
