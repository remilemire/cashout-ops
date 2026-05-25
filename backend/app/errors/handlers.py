# backend/app/errors/handlers.py

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .domain import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServerError,
    UnauthenticatedError,
    UnprocessableError,
)
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
from .translators import translate_validation_error
from .types import ErrorStatus, ErrorType


def init_error_handlers(app: FastAPI) -> None:

    # ================================
    # ------------ Domain ------------
    # ================================

    @app.exception_handler(ServerError)
    def handle_server_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: UnprocessableError
    ) -> JSONResponse:
        response = ServerErrorResponse()
        return format_error_response(response)

    @app.exception_handler(UnprocessableError)
    def handle_unprocessable_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: UnprocessableError
    ) -> JSONResponse:
        response = UnprocessableResponse(details=exc.details)
        return format_error_response(response)

    @app.exception_handler(ConflictError)
    def handle_conflict_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: ConflictError
    ) -> JSONResponse:
        response = ConflictResponse(details=exc.details)
        return format_error_response(response)

    @app.exception_handler(NotFoundError)
    def handle_not_found_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: NotFoundError
    ) -> JSONResponse:
        response = NotFoundResponse()
        return format_error_response(response)

    @app.exception_handler(ForbiddenError)
    def handle_forbidden_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: ForbiddenError
    ) -> JSONResponse:
        response = ForbiddenResponse()
        return format_error_response(response)

    @app.exception_handler(UnauthenticatedError)
    def handle_unauthenticated_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: UnauthenticatedError
    ) -> JSONResponse:
        response = UnauthenticatedResponse()
        return format_error_response(response)

    @app.exception_handler(BadRequestError)
    def handle_bad_request_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: BadRequestError
    ) -> JSONResponse:
        response = BadRequestResponse()
        return format_error_response(response)

    # ================================
    # ----------- Pydantic -----------
    # ================================

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    def handle_validation_error(  # type: ignore[reportUnusedFunction]
        request: Request,
        exc: ValidationError | RequestValidationError,
    ) -> JSONResponse:
        response = UnprocessableResponse(details=translate_validation_error(exc))
        return format_error_response(response)

    # ================================
    # ---------- Starlette -----------
    # ================================

    @app.exception_handler(StarletteHTTPException)
    def handle_http_exception(  # type: ignore[reportUnusedFunction]
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        match exc.status_code:
            case ErrorStatus.HTTP_400_BAD_REQUEST.value:
                response = BadRequestResponse()
            case ErrorStatus.HTTP_401_UNAUTHENTICATED.value:
                response = UnauthenticatedResponse()
            case ErrorStatus.HTTP_403_FORBIDDEN.value:
                response = ForbiddenResponse()
            case ErrorStatus.HTTP_404_NOT_FOUND.value:
                response = NotFoundResponse()
            case ErrorStatus.HTTP_409_CONFLICT.value:
                response = ConflictResponse()
            case ErrorStatus.HTTP_422_UNPROCESSABLE.value:
                response = UnprocessableResponse()
            case ErrorStatus.HTTP_500_SERVER_ERROR.value:
                response = ServerErrorResponse()
            case _:
                response = (
                    BadRequestResponse()
                    if 400 <= exc.status_code < 500
                    else ServerErrorResponse()
                )

        return format_error_response(response)

    # ================================
    # ----------- Uncaught -----------
    # ================================

    @app.exception_handler(Exception)
    def handle_uncaught_exception(  # type: ignore[reportUnusedFunction]
        request: Request, exc: Exception
    ) -> JSONResponse:
        response = ServerErrorResponse()
        return format_error_response(response)


# ================================
# ----------- Helpers ------------
# ================================


HTTP_CODE_MAP: Mapping[ErrorType, ErrorStatus] = {
    "bad_request": ErrorStatus.HTTP_400_BAD_REQUEST,
    "unauthenticated": ErrorStatus.HTTP_401_UNAUTHENTICATED,
    "forbidden": ErrorStatus.HTTP_403_FORBIDDEN,
    "not_found": ErrorStatus.HTTP_404_NOT_FOUND,
    "conflict": ErrorStatus.HTTP_409_CONFLICT,
    "unprocessable": ErrorStatus.HTTP_422_UNPROCESSABLE,
    "server_error": ErrorStatus.HTTP_500_SERVER_ERROR,
}


def format_error_response(error_response: ErrorResponse) -> JSONResponse:
    return JSONResponse(
        status_code=HTTP_CODE_MAP[error_response.type].value,
        content=error_response.to_response(),
    )
