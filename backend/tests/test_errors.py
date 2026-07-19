from __future__ import annotations

from datetime import UTC, datetime

import pytest
from psycopg import Error as PsycopgError
from psycopg.errors import ForeignKeyViolation, RestrictViolation
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors.translators import (
    translate_integrity_error,
    translate_validation_error,
)
from app.features.cashout.models import CashoutData, CashoutSubmission

from .factories import create_user


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


async def test_translate_real_postgres_restrict_violation_maps_constraint(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    submission = CashoutSubmission(
        submitted_by_user_id=user.id,
        submitted_at=datetime.now(UTC),
    )
    db_session.add(submission)
    await db_session.flush()
    db_session.add(CashoutData(submission_id=submission.id))
    await db_session.commit()

    with pytest.raises(IntegrityError) as caught:
        await db_session.execute(
            delete(CashoutSubmission).where(CashoutSubmission.id == submission.id)
        )

    # The violated constraint is registered in `constraint_to_code`, so the
    # translation lands on the cashout feature's code.
    translated = translate_integrity_error(caught.value)
    await db_session.rollback()

    assert translated.code == "SUBMISSION_HAS_DATA"


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
