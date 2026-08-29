# backend/tests/support/factories.py

"""Helpers for seeding database rows directly (bypassing the API)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cashout.data.model import CashoutData
from app.features.cashout.data.types import TipoutDepartment
from app.features.users.model import User
from app.features.users.types import UserRole


async def create_user(
    db: AsyncSession,
    *,
    email: str = "cashier@test.com",
    full_name: str = "Test User",
    role: UserRole = UserRole.STAFF,
) -> User:
    user = User(
        email=email,
        full_name=full_name,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def build_cashout_data(
    submission_id: UUID,
    *,
    tipout_departments: list[TipoutDepartment] | None = None,
) -> CashoutData:
    """A CashoutData with the columns completion always fills.

    The rates are what reconcile snapshots off settings; the source figures are
    left unset, as they are on a row reconcile writes today.
    """
    return CashoutData(
        submission_id=submission_id,
        tipout_departments=tipout_departments or [TipoutDepartment.KITCHEN],
        bar_tipout_rate=Decimal("0.0500"),
        kitchen_tipout_rate=Decimal("0.0300"),
        expo_tipout_rate=Decimal("0.0100"),
        host_tipout_rate=Decimal("0.0100"),
    )


__all__ = ["build_cashout_data", "create_user"]
