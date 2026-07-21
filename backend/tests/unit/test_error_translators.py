# backend/tests/unit/test_error_translators.py

from __future__ import annotations

import pytest
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


def test_translate_validation_error_builds_cataloged_issues() -> None:
    class Payload(BaseModel):
        display_name: str = Field(min_length=3)
        amount: int

    with pytest.raises(PydanticValidationError) as caught:
        Payload.model_validate({"display_name": "x", "amount": "not-a-number"})

    translated = translate_validation_error(caught.value)

    assert translated.code == "VALIDATION_FAILED"
    assert list(translated.issues) == [
        # Paths are camelCased to match the API's JSON casing.
        {"code": "TOO_SHORT", "path": ["displayName"], "ctx": {"min_length": 3}},
        {"code": "INTEGER_TYPE", "path": ["amount"]},
    ]
