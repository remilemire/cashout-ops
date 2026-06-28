# backend/app/errors/translators.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.lib.casing import snake_to_camel

from .catalog import VALIDATION_DETAILS
from .domain import (
    AlreadyExistsError,
    DomainError,
    InUseError,
    ServerError,
    UnprocessableError,
)
from .schemas import ErrorDetail
from .types import UnprocessableContext, ValidationRule

# ================================
# ----------- Pydantic -----------
# ================================


def translate_validation_error(
    exc: ValidationError | RequestValidationError,
) -> list[ErrorDetail]:
    return [_to_detail(e) for e in exc.errors()]


def _to_detail(error: Mapping[str, Any]) -> ErrorDetail:
    rule = PYDANTIC_TO_RULE.get(error.get("type", ""), ValidationRule.INVALID_VALUE)
    ctx = _to_context(error.get("ctx") or {})
    return ErrorDetail(
        rule=rule,
        detail=VALIDATION_DETAILS[rule](ctx),
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


def translate_integrity_error(exc: IntegrityError) -> DomainError:
    diag = getattr(exc.orig, "diag", None)
    sqlstate = getattr(diag, "sqlstate", None)
    return SQLSTATE_TO_ERROR.get(sqlstate or "", ServerError)()


# ================================
# ------------ Tables ------------
# ================================


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
SQLSTATE_TO_ERROR: Mapping[str, type[DomainError]] = {
    "23505": AlreadyExistsError,  # unique_violation
    "23503": InUseError,  # foreign_key_violation
    "23514": UnprocessableError,  # check_violation
    "23502": UnprocessableError,  # not_null_violation
}


_REQUEST_LOC_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})
