# backend/app/features/cashout/data/service.py

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cashout.analyses.model import CashoutDocumentAnalysis

from . import repository
from .model import CashoutData


async def reconcile(
    db: AsyncSession,
    *,
    submission_id: UUID,
    analyses: Sequence[CashoutDocumentAnalysis],
) -> CashoutData:
    """Build the submission's data row from its verified analyses and add it."""
    # TODO(document-ai): real reconciliation (cross-checking totals between the
    # verified analyses) once the extraction schemas define real fields. Until
    # then the placeholder columns stay NULL.
    _ = analyses
    data = CashoutData(submission_id=submission_id)
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
