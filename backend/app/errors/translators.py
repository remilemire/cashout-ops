# backend/app/errors/translators.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError

from app.lib.casing import snake_to_camel

from .app_error import AppError
from .catalog import ErrorCode
from .constraints import constraint_code_map
from .validation import (
    ValidationError,
    ValidationIssueCode,
    ValidationIssueContext,
    ValidationIssueData,
)

# ================================
# ---------- SQLAlchemy ----------
# ================================


def translate_integrity_error(error: IntegrityError) -> AppError:
    """Map a database integrity violation to its cataloged app error.

    A constraint registered in `constraint_code_map` yields its feature's code;
    anything else falls back by SQLSTATE class, so an unmapped violation still
    gets a sensible status.
    """
    constraint = _diag(error, "constraint_name")
    if constraint is not None and (code := constraint_code_map.get(constraint)):
        return AppError(code, str(error.orig))

    sqlstate = getattr(error.orig, "sqlstate", None) or _diag(error, "sqlstate")
    return AppError(_sqlstate_to_code.get(sqlstate or "", "INTERNAL"), str(error.orig))


def _diag(error: IntegrityError, attribute: str) -> str | None:
    diag = getattr(error.orig, "diag", None)
    value = getattr(diag, attribute, None)
    return value if isinstance(value, str) else None


# ================================
# ----------- Pydantic -----------
# ================================


def translate_validation_error(
    error: PydanticValidationError | RequestValidationError,
) -> ValidationError:
    """Flatten pydantic's error list into cataloged validation issues."""
    return ValidationError([_to_issue(e) for e in error.errors()])


def _to_issue(error: Mapping[str, Any]) -> ValidationIssueData:
    code = _pydantic_to_issue_code.get(error.get("type", ""), "INVALID_VALUE")
    path = _to_path(error.get("loc", ()))

    if ctx := _to_context(error.get("ctx") or {}):
        return {"code": code, "path": path, "ctx": ctx}
    return {"code": code, "path": path}


def _to_path(loc: tuple[int | str, ...]) -> list[str | int]:
    parts = list(loc)
    if parts and parts[0] in _REQUEST_LOC_PREFIXES:
        parts = parts[1:]

    return [snake_to_camel(part) if isinstance(part, str) else part for part in parts]


def _to_context(raw: Mapping[str, Any]) -> ValidationIssueContext:
    # Built as a plain dict because the context fields are ReadOnly; the cast
    # is safe since only cataloged keys are copied in.
    ctx = {
        name: raw[key]
        for key, name in _PYDANTIC_CTX_KEYS.items()
        if raw.get(key) is not None
    }
    return cast(ValidationIssueContext, ctx)


# ================================
# ------------ Tables ------------
# ================================


# Postgres class 23 (integrity_constraint_violation) SQLSTATEs.
_sqlstate_to_code: Mapping[str, ErrorCode] = {
    "23505": "CONFLICT",  # unique_violation
    "23503": "CONFLICT",  # foreign_key_violation
    "23001": "CONFLICT",  # restrict_violation
    "23514": "VALIDATION_FAILED",  # check_violation
    "23502": "VALIDATION_FAILED",  # not_null_violation
}


_pydantic_to_issue_code: Mapping[str, ValidationIssueCode] = {
    # Presence
    "missing": "MISSING_FIELD",
    "extra_forbidden": "EXTRA_FIELD",
    # Types
    "bool_type": "BOOLEAN_TYPE",
    "bool_parsing": "BOOLEAN_TYPE",
    "string_type": "STRING_TYPE",
    "string_unicode": "STRING_TYPE",
    "int_type": "INTEGER_TYPE",
    "int_parsing": "INTEGER_TYPE",
    "int_from_float": "INTEGER_TYPE",
    "float_type": "DECIMAL_TYPE",
    "float_parsing": "DECIMAL_TYPE",
    "decimal_type": "DECIMAL_TYPE",
    "decimal_parsing": "DECIMAL_TYPE",
    "dict_type": "OBJECT_TYPE",
    "list_type": "OBJECT_TYPE",
    "tuple_type": "OBJECT_TYPE",
    "set_type": "OBJECT_TYPE",
    "model_type": "OBJECT_TYPE",
    "model_attributes_type": "OBJECT_TYPE",
    # Range
    "greater_than": "TOO_SMALL",
    "greater_than_equal": "TOO_SMALL",
    "less_than": "TOO_LARGE",
    "less_than_equal": "TOO_LARGE",
    # Length
    "string_too_short": "TOO_SHORT",
    "string_too_long": "TOO_LONG",
    "too_short": "TOO_SHORT",
    "too_long": "TOO_LONG",
    # Options
    "enum": "INVALID_OPTION",
    "literal_error": "INVALID_OPTION",
    # Multiple
    "multiple_of": "INVALID_MULTIPLE",
}


# Pydantic ctx key → ValidationIssueContext key. Later entries win when both
# bounds appear (e.g. gt and ge).
_PYDANTIC_CTX_KEYS: Mapping[str, str] = {
    "gt": "min_value",
    "ge": "min_value",
    "lt": "max_value",
    "le": "max_value",
    "min_length": "min_length",
    "max_length": "max_length",
    "multiple_of": "multiple_of",
}


_REQUEST_LOC_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})

__all__ = ["translate_integrity_error", "translate_validation_error"]
