# backend/app/errors/handlers.py

from __future__ import annotations

from typing import TypedDict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthenticatedError,
    UnprocessableError,
)
from app.schemas.base import BaseOut


def init_error_handlers(app: FastAPI) -> None:

    # ================================
    # ------------ Domain ------------
    # ================================

    @app.exception_handler(BadRequestError)
    def handle_bad_request_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: BadRequestError
    ) -> JSONResponse:
        return _format_response(**_ERROR_DATA["bad request"])

    @app.exception_handler(NotFoundError)
    def handle_not_found_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: NotFoundError
    ) -> JSONResponse:
        return _format_response(**_ERROR_DATA["not found"])

    @app.exception_handler(ForbiddenError)
    def handle_forbidden_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: ForbiddenError
    ) -> JSONResponse:
        return _format_response(**_ERROR_DATA["forbidden"])

    @app.exception_handler(UnauthenticatedError)
    def handle_unauthenticated_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: UnauthenticatedError
    ) -> JSONResponse:
        return _format_response(**_ERROR_DATA["unauthenticated"])

    @app.exception_handler(UnprocessableError)
    def handle_unprocessable_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: UnprocessableError
    ) -> JSONResponse:
        return _format_response(**_ERROR_DATA["unprocessable"])

    @app.exception_handler(ConflictError)
    def handle_conflict_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: ConflictError
    ) -> JSONResponse:
        return _format_response(**_ERROR_DATA["conflict"])

    # ================================
    # ----------- Pydantic -----------
    # ================================

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    def handle_validation_error(  # type: ignore[reportUnusedFunction]
        request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        return _format_response(**_ERROR_DATA["unprocessable"])

    # ================================
    # ----------- Fast API -----------
    # ================================

    @app.exception_handler(HTTPException)
    @app.exception_handler(StarletteHTTPException)
    def handle_http_exception(  # type: ignore[reportUnusedFunction]
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        data: ErrorData
        match exc.status_code:
            case 400:
                data = _ERROR_DATA["bad request"]
            case 401:
                data = _ERROR_DATA["unauthenticated"]
            case 403:
                data = _ERROR_DATA["forbidden"]
            case 404:
                data = _ERROR_DATA["not found"]
            case 409:
                data = _ERROR_DATA["conflict"]
            case 422:
                data = _ERROR_DATA["unprocessable"]
            case _:
                data = _ERROR_DATA["service"]
        return _format_response(**data)

    # ================================
    # ----------- Uncaught -----------
    # ================================

    @app.exception_handler(Exception)
    def handle_uncaught_exception(  # type: ignore[reportUnusedFunction]
        request: Request, exc: Exception
    ) -> JSONResponse:
        return _format_response(**_ERROR_DATA["service"])


# ================================
# ------------ Schemas -----------
# ================================


class ErrorData(TypedDict):
    status: int
    type: str
    message: str


class ErrorSchema(BaseOut):
    type: str
    message: str
    details: dict[str, str] | None = None


# ================================
# ----------- Metadata -----------
# ================================


_ERROR_DATA: dict[
    str,
    ErrorData,
] = {
    "bad request": ErrorData(
        status=400,
        type="BadRequestError",
        message="The request could not be processed.",
    ),
    "not found": ErrorData(
        status=404,
        type="NotFoundError",
        message="The requested resource could not be found.",
    ),
    "unauthenticated": ErrorData(
        status=401, type="UnauthenticatedError", message="Authentication required."
    ),
    "forbidden": ErrorData(
        status=403,
        type="ForbiddenError",
        message="You do not have permission to perform this action.",
    ),
    "unprocessable": ErrorData(
        status=422,
        type="UnprocessableEntityError",
        message="There was a problem with the submission.",
    ),
    "conflict": ErrorData(
        status=409, type="ConflictError", message="There was a conflict."
    ),
    "service": ErrorData(
        status=500, type="ServiceError", message="Something went wrong."
    ),
}


# ================================
# ---------- Formatters ----------
# ================================


def _format_response(
    *, status: int, type: str, message: str, details: dict[str, str] | None = None
) -> JSONResponse:
    content = ErrorSchema(type=type, message=message)
    content.details = details
    return JSONResponse(
        status_code=status,
        content={"error": content.model_dump(by_alias=True, exclude_none=True)},
    )
