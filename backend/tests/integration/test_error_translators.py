# backend/tests/integration/test_error_translators.py

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors.translators import translate_integrity_error
from app.features.cashout.models import CashoutData, CashoutSubmission
from tests.support.factories import create_user


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
