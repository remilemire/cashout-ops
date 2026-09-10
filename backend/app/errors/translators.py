from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from math import isfinite
from typing import Any

from fastapi.exceptions import RequestValidationError
from pydantic import JsonValue
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError

from app.lib.casing import snake_to_camel

from .app_error import AppError
from .catalog import ErrorCode
from .constraints import constraint_code_map
from .validation import ValidationError, ValidationIssue


def translate_integrity_error(error: IntegrityError) -> AppError:
    """Prefer a feature's constraint code, then fall back to SQLSTATE."""
    constraint = _diag(error, "constraint_name")
    if constraint is not None and (code := constraint_code_map.get(constraint)):
        return AppError(code, str(error.orig))

    sqlstate = getattr(error.orig, "sqlstate", None) or _diag(error, "sqlstate")
    return AppError(_SQLSTATE_CODES.get(sqlstate or "", "INTERNAL"), str(error.orig))


def _diag(error: IntegrityError, attribute: str) -> str | None:
    diag = getattr(error.orig, "diag", None)
    value = getattr(diag, attribute, None)
    return value if isinstance(value, str) else None


def translate_validation_error(
    error: PydanticValidationError | RequestValidationError,
) -> ValidationError:
    """Keep Pydantic codes; omit input, messages, URLs, and exception objects."""
    issues: list[ValidationIssue] = []
    for detail in error.errors():
        path = list(detail["loc"])
        if (
            isinstance(error, RequestValidationError)
            and path
            and path[0] in _REQUEST_LOC_PREFIXES
        ):
            path = path[1:]
        issues.append(
            ValidationIssue(
                code=detail["type"],
                path=[
                    snake_to_camel(part) if isinstance(part, str) else part
                    for part in path
                ],
                ctx=_validation_context(detail.get("ctx") or {}),
            )
        )
    return ValidationError(issues)


def _validation_context(raw: Mapping[str, Any]) -> dict[str, JsonValue]:
    # Only schema constraints are public. In particular, `error` and `reason`
    # can contain exception messages or submitted values. Never stringify them.
    ctx: dict[str, JsonValue] = {}
    for key in _CONSTRAINT_KEYS:
        value = raw.get(key)
        if isinstance(value, Decimal) and value.is_finite():
            ctx[snake_to_camel(key)] = str(value)
        elif isinstance(value, (str, int, bool)):
            ctx[snake_to_camel(key)] = value
        elif isinstance(value, float) and isfinite(value):
            ctx[snake_to_camel(key)] = value
    return ctx


_SQLSTATE_CODES: Mapping[str, ErrorCode] = {
    "23505": "CONFLICT",  # unique_violation
    "23503": "CONFLICT",  # foreign_key_violation
    "23001": "CONFLICT",  # restrict_violation
    "23514": "VALIDATION_FAILED",  # check_violation
    "23502": "VALIDATION_FAILED",  # not_null_violation
}

_CONSTRAINT_KEYS = (
    "gt",
    "ge",
    "lt",
    "le",
    "min_length",
    "max_length",
    "multiple_of",
    "expected",
    "pattern",
    "max_digits",
    "decimal_places",
    "whole_digits",
)
_REQUEST_LOC_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})

__all__ = ["translate_integrity_error", "translate_validation_error"]
