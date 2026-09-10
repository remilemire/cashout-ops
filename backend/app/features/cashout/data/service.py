from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.cashout.analyses.model import CashoutDocumentAnalysis

from . import repository
from .model import CashoutData
from .reconciliation import reconcile_figures
from .schemas import CashoutAdjustmentIn
from .types import TipoutDepartment


async def reconcile(
    db: AsyncSession,
    *,
    submission_id: UUID,
    analyses: Sequence[CashoutDocumentAnalysis],
    tipout_departments: set[TipoutDepartment],
    adjustment: CashoutAdjustmentIn | None,
) -> CashoutData:
    """Build the submission's data row from its verified analyses and add it.

    The source figures come from `reconciliation`, which cross-checks the
    documents against each other first — a cashout that does not add up
    raises there and never reaches a row.

    `adjustment` is an admin's correction to that cross-check (the caller
    decides who may supply one): its deposit is subtracted from the report's
    card payments before they are compared to the summaries, and the deposit
    and its note are kept on the row so it explains its figures. The stored
    card payments stay the report's own figure.

    `tipout_departments` is the cashier's selection. The manager tips out on
    every cashout, so it is added here whatever the selection says — this is
    the one place that rule lives; a selection that already names the manager
    is accepted as is.

    The rates are copied onto the row rather than read back later: a cashout
    closes against the rates in force at that moment, and editing them
    afterwards must not restate it.
    """
    figures = reconcile_figures(
        analyses,
        deposit_total=adjustment.deposit_total if adjustment else Decimal(0),
    )
    departments = {*tipout_departments, TipoutDepartment.MANAGER}

    rates = settings.tipout
    data = CashoutData(
        submission_id=submission_id,
        food_net_sales=figures.food_net_sales,
        drink_net_sales=figures.drink_net_sales,
        total_net_sales=figures.total_net_sales,
        card_payment_total=figures.card_payment_total,
        cash_payment_total=figures.cash_payment_total,
        card_tip_total=figures.card_tip_total,
        deposit_total=adjustment.deposit_total if adjustment else None,
        adjustment_note=adjustment.note if adjustment else None,
        # Sorted so the stored order does not depend on set iteration order.
        tipout_departments=sorted(departments),
        bar_tipout_rate=rates.BAR_RATE,
        kitchen_tipout_rate=rates.KITCHEN_RATE,
        expo_tipout_rate=rates.EXPO_RATE,
        host_tipout_rate=rates.HOST_RATE,
        manager_tipout_rate=rates.MANAGER_RATE,
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
