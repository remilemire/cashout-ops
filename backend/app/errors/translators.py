# backend/app/errors/translators.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.lib.casing import snake_to_camel

from .catalog import CATALOG
from .domain import (
    AlreadyExistsError,
    AppError,
    BadRequestError,
    ForbiddenError,
    InUseError,
    NotFoundError,
    ServerError,
    UnauthorizedError,
    UnprocessableError,
)
from .schemas import ErrorBody, ErrorDetail, ErrorResponse
from .types import UnprocessableContext, ValidationRule

# ================================
# ------------ Entry -------------
# ================================


def translate_error(exc: Exception) -> JSONResponse:
    """Turn any raised exception into the canonical error `JSONResponse`.

    The single entry point for the exception handlers: it maps the exception to
    an `AppError` (translation) and serializes the catalog-backed body
    (formatting). Anything unrecognized becomes a `ServerError`.
    """
    return _format_response(_build_response(_to_app_error(exc)))


def _to_app_error(exc: Exception) -> AppError:
    if isinstance(exc, AppError):
        return exc
    if isinstance(exc, (ValidationError, RequestValidationError)):
        return UnprocessableError(errors=_translate_validation_error(exc))
    if isinstance(exc, IntegrityError):
        return translate_integrity_error(exc)
    if isinstance(exc, StarletteHTTPException):
        return _http_error(exc.status_code)
    return ServerError()


# ================================
# ----------- Response -----------
# ================================


def _build_response(exc: AppError) -> ErrorResponse:
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


def _format_response(response: ErrorResponse) -> JSONResponse:
    # Error handlers return JSONResponse directly, so there's no router
    # response_model to serialize the body for us — do it here.
    return JSONResponse(
        status_code=response.status,
        content=response.body.model_dump(by_alias=True, exclude_none=True, mode="json"),
    )


# ================================
# ----------- Pydantic -----------
# ================================


def _translate_validation_error(
    exc: ValidationError | RequestValidationError,
) -> list[ErrorDetail]:
    return [_to_detail(e) for e in exc.errors()]


def _to_detail(error: Mapping[str, Any]) -> ErrorDetail:
    rule = PYDANTIC_TO_RULE.get(error.get("type", ""), ValidationRule.INVALID_VALUE)
    # `detail` is omitted so ErrorDetail fills it from the catalog using `ctx`.
    return ErrorDetail.build(
        rule,
        ctx=_to_context(error.get("ctx") or {}),
        path=_to_path(error.get("loc", ())),
    )


def _to_path(loc: tuple[int | str, ...]) -> list[str | int]:
    parts = list(loc)
    if parts and parts[0] in _REQUEST_LOC_PREFIXES:
        parts = parts[1:]

    return [snake_to_camel(part) if isinstance(part, str) else part for part in parts]


def _to_context(raw: Mapping[str, Any]) -> UnprocessableContext:
    ctx: UnprocessableContext = {}

    if (value := raw.get("gt", raw.get("ge"))) is not None:
        ctx["min_value"] = value
    if (value := raw.get("lt", raw.get("le"))) is not None:
        ctx["max_value"] = value
    if (value := raw.get("min_length")) is not None:
        ctx["min_length"] = value
    if (value := raw.get("max_length")) is not None:
        ctx["max_length"] = value
    if (value := raw.get("multiple_of")) is not None:
        ctx["multiple_of"] = value

    return ctx


# ================================
# ---------- SQLAlchemy ----------
# ================================


def translate_integrity_error(exc: IntegrityError) -> AppError:
    sqlstate = getattr(exc.orig, "sqlstate", None)
    if sqlstate is None:
        diag = getattr(exc.orig, "diag", None)
        sqlstate = getattr(diag, "sqlstate", None)
    return SQLSTATE_TO_ERROR.get(sqlstate or "", ServerError)()


# ================================
# ---------- Starlette -----------
# ================================


def _http_error(status_code: int) -> AppError:
    factory = STATUS_TO_ERROR.get(status_code)
    if factory is not None:
        return factory()
    return BadRequestError() if 400 <= status_code < 500 else ServerError()


# ================================
# ------------ Tables ------------
# ================================


STATUS_TO_ERROR: Mapping[int, type[AppError]] = {
    status.HTTP_400_BAD_REQUEST: BadRequestError,
    status.HTTP_401_UNAUTHORIZED: UnauthorizedError,
    status.HTTP_403_FORBIDDEN: ForbiddenError,
    status.HTTP_404_NOT_FOUND: NotFoundError,
    status.HTTP_409_CONFLICT: AlreadyExistsError,
    status.HTTP_422_UNPROCESSABLE_CONTENT: UnprocessableError,
    status.HTTP_500_INTERNAL_SERVER_ERROR: ServerError,
}


PYDANTIC_TO_RULE: Mapping[str, ValidationRule] = {
    # Presence
    "missing": ValidationRule.MISSING_FIELD,
    "extra_forbidden": ValidationRule.EXTRA_FIELD,
    # Types
    "bool_type": ValidationRule.BOOLEAN_TYPE,
    "bool_parsing": ValidationRule.BOOLEAN_TYPE,
    "string_type": ValidationRule.STRING_TYPE,
    "string_unicode": ValidationRule.STRING_TYPE,
    "int_type": ValidationRule.INTEGER_TYPE,
    "int_parsing": ValidationRule.INTEGER_TYPE,
    "int_from_float": ValidationRule.INTEGER_TYPE,
    "float_type": ValidationRule.DECIMAL_TYPE,
    "float_parsing": ValidationRule.DECIMAL_TYPE,
    "decimal_type": ValidationRule.DECIMAL_TYPE,
    "decimal_parsing": ValidationRule.DECIMAL_TYPE,
    "dict_type": ValidationRule.OBJECT_TYPE,
    "list_type": ValidationRule.OBJECT_TYPE,
    "tuple_type": ValidationRule.OBJECT_TYPE,
    "set_type": ValidationRule.OBJECT_TYPE,
    "model_type": ValidationRule.OBJECT_TYPE,
    "model_attributes_type": ValidationRule.OBJECT_TYPE,
    # Range
    "greater_than": ValidationRule.TOO_SMALL,
    "greater_than_equal": ValidationRule.TOO_SMALL,
    "less_than": ValidationRule.TOO_LARGE,
    "less_than_equal": ValidationRule.TOO_LARGE,
    # Length
    "string_too_short": ValidationRule.TOO_SHORT,
    "string_too_long": ValidationRule.TOO_LONG,
    "too_short": ValidationRule.TOO_SHORT,
    "too_long": ValidationRule.TOO_LONG,
    # Options
    "enum": ValidationRule.INVALID_OPTION,
    "literal_error": ValidationRule.INVALID_OPTION,
    # Multiple
    "multiple_of": ValidationRule.INVALID_MULTIPLE,
}


# Postgres class 23 (integrity_constraint_violation) SQLSTATEs.
SQLSTATE_TO_ERROR: Mapping[str, type[AppError]] = {
    "23505": AlreadyExistsError,  # unique_violation
    "23503": InUseError,  # foreign_key_violation
    "23001": InUseError,  # restrict_violation
    "23514": UnprocessableError,  # check_violation
    "23502": UnprocessableError,  # not_null_violation
}


_REQUEST_LOC_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})
