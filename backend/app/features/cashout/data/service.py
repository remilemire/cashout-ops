# backend/app/features/cashout/data/service.py

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.cashout.analyses.model import CashoutDocumentAnalysis

from . import repository
from .model import CashoutData
from .types import TipoutDepartment


async def reconcile(
    db: AsyncSession,
    *,
    submission_id: UUID,
    analyses: Sequence[CashoutDocumentAnalysis],
    tipout_departments: set[TipoutDepartment],
) -> CashoutData:
    """Build the submission's data row from its verified analyses and add it.

    The rates are copied onto the row rather than read back later: a cashout
    closes against the rates in force at that moment, and editing them
    afterwards must not restate it.
    """
    # TODO(document-ai): reconcile the verified analyses into the source
    # figures (food/drink/total net sales, card/cash payment totals, card tip
    # total). Until then they stay null and every generated tipout with them.
    _ = analyses

    rates = settings.tipout
    data = CashoutData(
        submission_id=submission_id,
        # Sorted so the stored order does not depend on set iteration order.
        tipout_departments=sorted(tipout_departments),
        bar_tipout_rate=rates.BAR_RATE,
        kitchen_tipout_rate=rates.KITCHEN_RATE,
        expo_tipout_rate=rates.EXPO_RATE,
        host_tipout_rate=rates.HOST_RATE,
    )
    await repository.add_data(db, data)
    return data


async def delete_for_submission(
    db: AsyncSession, *, submission_id: UUID
) -> CashoutData | None:
    """Drop the submission's reconciled data row; returns it, or None if absent."""
    data = await repository.find_data_by_submission(db, submission_id=submission_id)
    if data is not None:
        await repository.delete_data(db, data)
    return data


async def list_data(db: AsyncSession) -> Sequence[CashoutData]:
    """Every reconciled cashout data row, newest first (admin table)."""
    return await repository.list_data(db)


__all__ = [
    "reconcile",
    "delete_for_submission",
    "list_data",
]
