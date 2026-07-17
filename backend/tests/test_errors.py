from __future__ import annotations

from datetime import UTC, datetime

import pytest
from psycopg import Error as PsycopgError
from psycopg.errors import ForeignKeyViolation, RestrictViolation
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import InUseError
from app.errors.translators import translate_integrity_error
from app.features.cashout.models import CashoutData, CashoutSubmission

from .factories import create_user


@pytest.mark.parametrize(
    ("original", "sqlstate"),
    [
        (ForeignKeyViolation("foreign key violation"), "23503"),
        (RestrictViolation("restrict violation"), "23001"),
    ],
)
def test_translate_integrity_error_reads_psycopg_sqlstate(
    original: PsycopgError,
    sqlstate: str,
) -> None:
    error = IntegrityError("DELETE", {}, original)

    translated = translate_integrity_error(error)

    assert original.sqlstate == sqlstate
    assert original.diag.sqlstate is None
    assert isinstance(translated, InUseError)


async def test_translate_real_postgres_foreign_key_violation(
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

    translated = translate_integrity_error(caught.value)
    await db_session.rollback()

    assert isinstance(translated, InUseError)
