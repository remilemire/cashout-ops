# backend/app/errors/handlers.py

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .app_error import AppError
from .catalog import error_catalog, kind_status_map
from .codes import ErrorCode
from .schemas import ErrorResponseSchema, ValidationIssueSchema
from .translators import translate_integrity_error, translate_validation_error
from .validation import ValidationError, validation_issue_catalog


def init_error_handlers(app: FastAPI) -> None:
    # Every failure mode funnels into `_to_response`: recognized exceptions are
    # translated to an `AppError` and formatted from the catalog; anything
    # unrecognized becomes a 500 INTERNAL. The registrations differ only in the
    # exception type they catch — kept separate so ours override FastAPI's
    # built-in RequestValidationError / HTTPException handlers and so
    # recognized errors are resolved on the inner middleware rather than
    # re-raised as 500s.

    @app.exception_handler(AppError)
    def handle_app_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: AppError
    ) -> JSONResponse:
        return _to_response(exc)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(PydanticValidationError)
    def handle_validation_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: PydanticValidationError | RequestValidationError
    ) -> JSONResponse:
        return _to_response(translate_validation_error(exc))

    @app.exception_handler(IntegrityError)
    def handle_integrity_error(  # type: ignore[reportUnusedFunction]
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        return _to_response(translate_integrity_error(exc))

    @app.exception_handler(StarletteHTTPException)
    def handle_http_exception(  # type: ignore[reportUnusedFunction]
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _to_response(AppError(_to_code(exc.status_code)))

    @app.exception_handler(Exception)
    def handle_uncaught_exception(  # type: ignore[reportUnusedFunction]
        request: Request, exc: Exception
    ) -> JSONResponse:
        return _to_response(AppError("INTERNAL"))


# ================================
# ----------- Response -----------
# ================================


def _to_response(error: AppError) -> JSONResponse:
    entry = error_catalog[error.code]
    # The catalog message is the only one clients see; AppError.message is
    # internal-only context and must not leak here.
    body = ErrorResponseSchema(
        kind=entry["kind"],
        code=error.code,
        message=entry["message"],
        issues=_to_issue_schemas(error) if isinstance(error, ValidationError) else None,
    )
    # Error handlers return JSONResponse directly, so there's no router
    # response_model to serialize the body for us — do it here.
    return JSONResponse(
        status_code=kind_status_map[entry["kind"]],
        content=body.model_dump(by_alias=True, exclude_none=True, mode="json"),
    )


def _to_issue_schemas(error: ValidationError) -> list[ValidationIssueSchema]:
    return [
        ValidationIssueSchema(
            code=issue["code"],
            path=list(issue["path"]),
            message=validation_issue_catalog[issue["code"]]["create_message"](
                issue.get("ctx", {})
            ),
        )
        for issue in error.issues
    ]


# ================================
# ---------- Starlette -----------
# ================================


def _to_code(status_code: int) -> ErrorCode:
    """Map a raw Starlette HTTPException status to a base code.

    The detail string is discarded on purpose — it can carry internals that
    must not reach the client; the catalog message is used instead.
    """
    code = _status_to_code.get(status_code)
    if code is not None:
        return code
    return "BAD_REQUEST" if 400 <= status_code < 500 else "INTERNAL"


_status_to_code: Mapping[int, ErrorCode] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHENTICATED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "ROUTE_NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "VALIDATION_FAILED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}

__all__ = ["init_error_handlers"]
