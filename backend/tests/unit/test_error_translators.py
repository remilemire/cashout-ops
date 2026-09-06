# backend/tests/unit/test_error_translators.py

from __future__ import annotations

from decimal import Decimal
from typing import Literal

import pytest
from fastapi.exceptions import RequestValidationError
from psycopg import Error as PsycopgError
from psycopg.errors import ForeignKeyViolation, RestrictViolation
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError

from app.errors.translators import (
    translate_integrity_error,
    translate_validation_error,
)


@pytest.mark.parametrize(
    ("original", "sqlstate"),
    [
        (ForeignKeyViolation("foreign key violation"), "23503"),
        (RestrictViolation("restrict violation"), "23001"),
    ],
)
def test_translate_integrity_error_falls_back_to_sqlstate(
    original: PsycopgError,
    sqlstate: str,
) -> None:
    # No constraint name in the diagnostics → the SQLSTATE class decides.
    error = IntegrityError("DELETE", {}, original)

    translated = translate_integrity_error(error)

    assert original.sqlstate == sqlstate
    assert original.diag.sqlstate is None
    assert translated.code == "CONFLICT"


def test_translate_validation_error_preserves_codes_and_constraints() -> None:
    class Payload(BaseModel):
        display_name: str = Field(min_length=3)
        amount: int

    with pytest.raises(PydanticValidationError) as caught:
        Payload.model_validate({"display_name": "x", "amount": "not-a-number"})

    translated = translate_validation_error(caught.value)

    assert translated.code == "VALIDATION_FAILED"
    assert [issue.model_dump() for issue in translated.issues] == [
        # Paths are camelCased to match the API's JSON casing.
        {"code": "string_too_short", "path": ["displayName"], "ctx": {"minLength": 3}},
        {"code": "int_parsing", "path": ["amount"], "ctx": {}},
    ]


@pytest.mark.parametrize("prefix", ["body", "query", "path", "header", "cookie"])
def test_request_paths_strip_only_the_transport_prefix(prefix: str) -> None:
    error = RequestValidationError(
        [
            {"type": "missing", "loc": (prefix, "line_items", 0, "full_name")},
        ]
    )

    [issue] = translate_validation_error(error).issues

    assert issue.path == ["lineItems", 0, "fullName"]
    assert issue.ctx == {}


def test_model_field_named_body_is_not_mistaken_for_a_request_prefix() -> None:
    class Payload(BaseModel):
        body: int

    with pytest.raises(PydanticValidationError) as caught:
        Payload.model_validate({})

    assert translate_validation_error(caught.value).issues[0].path == ["body"]


def test_constraints_preserve_inclusive_bounds_decimal_precision_and_choices() -> None:
    class Payload(BaseModel):
        minimum: int = Field(ge=0)
        maximum: Decimal = Field(lt=Decimal("1.000000000000000001"))
        role: Literal["staff", "admin"]

    with pytest.raises(PydanticValidationError) as caught:
        Payload.model_validate({"minimum": -1, "maximum": 2, "role": "owner"})

    assert [
        issue.model_dump() for issue in translate_validation_error(caught.value).issues
    ] == [
        {"code": "greater_than_equal", "path": ["minimum"], "ctx": {"ge": 0}},
        {
            "code": "less_than",
            "path": ["maximum"],
            "ctx": {"lt": "1.000000000000000001"},
        },
        {
            "code": "literal_error",
            "path": ["role"],
            "ctx": {"expected": "'staff' or 'admin'"},
        },
    ]


def test_validation_does_not_expose_input_exception_details_or_unsafe_context() -> None:
    secret = "private submitted value"
    error = RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "password"),
                "input": secret,
                "msg": secret,
                "url": "https://example.invalid/internal",
                "ctx": {
                    "error": ValueError(secret),
                    "reason": secret,
                    "min_length": 8,
                    "max_length": object(),
                    "gt": float("inf"),
                    "le": Decimal("NaN"),
                },
            },
        ]
    )

    [issue] = translate_validation_error(error).issues

    assert issue.model_dump() == {
        "code": "value_error",
        "path": ["password"],
        "ctx": {"minLength": 8},
    }
    assert secret not in issue.model_dump_json()


def test_unrecognized_integrity_errors_keep_diagnostics_private() -> None:
    translated = translate_integrity_error(
        IntegrityError("SQL", {}, Exception("private SQL"))
    )

    assert translated.code == "INTERNAL"
    assert translated.ctx == {}
    assert translated.message == "private SQL"
