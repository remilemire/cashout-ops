# backend/app/errors/handlers.py

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .domain import AppError
from .translators import translate_error


def init_error_handlers(app: FastAPI) -> None:
    # Every handler funnels into `translate_error`, which owns all translation
    # and response formatting. The registrations differ only in the exception
    # type they catch — kept separate so ours override FastAPI's built-in
    # RequestValidationError / HTTPException handlers and so recognized errors
    # are resolved on the inner middleware rather than re-raised as 500s.

    @app.exception_handler(AppError)
    def handle_app_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: AppError
    ) -> JSONResponse:
        return translate_error(exc)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    def handle_validation_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: ValidationError | RequestValidationError
    ) -> JSONResponse:
        return translate_error(exc)

    @app.exception_handler(IntegrityError)
    def handle_integrity_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        return translate_error(exc)

    @app.exception_handler(StarletteHTTPException)
    def handle_http_exception(  # type: ignore[reportUnusedFunction]
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return translate_error(exc)

    @app.exception_handler(Exception)
    def handle_uncaught_exception(  # type: ignore[reportUnusedFunction]
        request: Request, exc: Exception
    ) -> JSONResponse:
        return translate_error(exc)
