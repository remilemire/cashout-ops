from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .app_error import AppError
from .catalog import ErrorCode, error_kind_map, kind_status_map
from .rate_limit import RateLimitedError
from .schemas import ErrorResponseSchema
from .translators import translate_integrity_error, translate_validation_error
from .validation import ValidationError


def init_error_handlers(app: FastAPI) -> None:
    # Register recognized exceptions explicitly to override FastAPI defaults.

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
    kind = error_kind_map[error.code]
    body = ErrorResponseSchema(
        kind=kind,
        code=error.code,
        ctx=error.ctx,
        issues=error.issues if isinstance(error, ValidationError) else None,
    )
    # Error handlers return JSONResponse directly, so there's no router
    # response_model to serialize the body for us — do it here.
    return JSONResponse(
        status_code=kind_status_map[kind],
        content=body.model_dump(by_alias=True, exclude_none=True, mode="json"),
        headers=(
            {"Retry-After": str(error.retry_after_seconds)}
            if isinstance(error, RateLimitedError)
            else None
        ),
    )


# ================================
# ---------- Starlette -----------
# ================================


def _to_code(status_code: int) -> ErrorCode:
    """Map a raw Starlette HTTPException status to a base code.

    The detail string is discarded on purpose — it can carry internals that
    must not reach the client; only the mapped code is used.
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
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}

__all__ = ["init_error_handlers"]
