# backend/app/errors/translators.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from .schemas import UnprocessableDetail
from .types import UnprocessableCode, UnprocessableContext

# ================================
# ----------- Pydantic -----------
# ================================


def translate_validation_error(
    exc: ValidationError | RequestValidationError,
) -> list[UnprocessableDetail]:
    return [_to_detail(e) for e in exc.errors()]


def _to_detail(error: Mapping[str, Any]) -> UnprocessableDetail:
    return UnprocessableDetail(
        field=_to_field(error.get("loc", ())),
        code=PYDANTIC_TO_CODE.get(error.get("type", ""), "invalid_value"),
        ctx=_to_context(error.get("ctx") or {}),
    )


def _to_field(loc: tuple[int | str, ...]) -> str:
    parts = list(loc)
    if parts and parts[0] in _REQUEST_LOC_PREFIXES:
        parts = parts[1:]

    pieces: list[str] = []
    for part in parts:
        if isinstance(part, int):
            pieces.append(f"[{part}]")
        elif pieces:
            pieces.append(f".{part}")
        else:
            pieces.append(part)

    return "".join(pieces)


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
# ------------ Tables ------------
# ================================


PYDANTIC_TO_CODE: Mapping[str, UnprocessableCode] = {
    # Presence
    "missing": "missing_field",
    "extra_forbidden": "extra_field",
    # Types
    "bool_type": "boolean_type",
    "bool_parsing": "boolean_type",
    "string_type": "string_type",
    "string_unicode": "string_type",
    "int_type": "integer_type",
    "int_parsing": "integer_type",
    "int_from_float": "integer_type",
    "float_type": "decimal_type",
    "float_parsing": "decimal_type",
    "decimal_type": "decimal_type",
    "decimal_parsing": "decimal_type",
    "dict_type": "object_type",
    "list_type": "object_type",
    "tuple_type": "object_type",
    "set_type": "object_type",
    "model_type": "object_type",
    "model_attributes_type": "object_type",
    # Range
    "greater_than": "too_small",
    "greater_than_equal": "too_small",
    "less_than": "too_large",
    "less_than_equal": "too_large",
    # Length
    "string_too_short": "too_short",
    "string_too_long": "too_long",
    "too_short": "too_short",
    "too_long": "too_long",
    # Options
    "enum": "invalid_option",
    "literal_error": "invalid_option",
    # Multiple
    "multiple_of": "invalid_multiple",
}


_REQUEST_LOC_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})
