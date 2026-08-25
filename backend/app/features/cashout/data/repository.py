# backend/app/features/cashout/data/repository.py

"""Database access for cashout data; only the data service imports this."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import CashoutData


async def add_data(db: AsyncSession, data: CashoutData) -> None:
    db.add(data)


async def find_data_by_submission(
    db: AsyncSession, *, submission_id: UUID
) -> CashoutData | None:
    stmt = select(CashoutData).where(CashoutData.submission_id == submission_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def delete_data(db: AsyncSession, data: CashoutData) -> None:
    await db.delete(data)
    # Flush so the RESTRICT FK on cashout_data no longer sees the row when the
    # submission itself is deleted in the same transaction.
    await db.flush()


async def list_data(db: AsyncSession) -> Sequence[CashoutData]:
    stmt = select(CashoutData).order_by(CashoutData.created_at.desc())
    return (await db.execute(stmt)).scalars().all()


__all__ = [
    "add_data",
    "find_data_by_submission",
    "delete_data",
    "list_data",
]
