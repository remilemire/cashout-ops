from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors.translators import translate_integrity_error
from app.features.cashout.models import CashoutSubmission
from app.features.users.types import UserRole
from tests.support.factories import build_cashout_data, create_user


async def test_translate_real_postgres_restrict_violation_maps_constraint(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    submission = CashoutSubmission(
        employee_user_id=user.id,
        submitted_at=datetime.now(UTC),
        business_date=date.today(),
    )
    db_session.add(submission)
    await db_session.flush()
    db_session.add(build_cashout_data(submission.id))
    await db_session.commit()

    with pytest.raises(IntegrityError) as caught:
        await db_session.execute(
            delete(CashoutSubmission).where(CashoutSubmission.id == submission.id)
        )

    # The violated constraint is registered in `constraint_code_map`, so the
    # translation lands on the cashout feature's code.
    translated = translate_integrity_error(caught.value)
    await db_session.rollback()

    assert translated.code == "SUBMISSION_HAS_DATA"


async def test_translate_real_postgres_single_owner_violation_maps_constraint(
    db_session: AsyncSession,
) -> None:
    await create_user(db_session, email="owner@test.com", role=UserRole.OWNER)

    with pytest.raises(IntegrityError) as caught:
        await create_user(db_session, email="usurper@test.com", role=UserRole.OWNER)

    # ix_users_single_owner is registered in `constraint_code_map`, so the
    # translation lands on the users feature's code.
    translated = translate_integrity_error(caught.value)
    await db_session.rollback()

    assert translated.code == "OWNER_ALREADY_EXISTS"
