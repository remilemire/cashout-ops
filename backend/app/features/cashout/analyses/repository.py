"""Database access for cashout analyses."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cashout.submissions.repository import (
    get_submission as get_live_submission,
)
from app.features.cashout.uploads.repository import get_upload

from .model import CashoutDocumentAnalysis


async def get_analysis(
    db: AsyncSession, *, analysis_id: UUID
) -> CashoutDocumentAnalysis | None:
    return await db.get(CashoutDocumentAnalysis, analysis_id)


async def list_analyses_for_upload(
    db: AsyncSession, *, upload_id: UUID
) -> Sequence[CashoutDocumentAnalysis]:
    """An upload's analyses in position order: one per document found in
    the upload."""
    stmt = (
        select(CashoutDocumentAnalysis)
        .where(CashoutDocumentAnalysis.cashout_upload_id == upload_id)
        .order_by(CashoutDocumentAnalysis.position)
    )
    return (await db.execute(stmt)).scalars().all()


async def count_analyses(db: AsyncSession, *, upload_id: UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(CashoutDocumentAnalysis)
        .where(CashoutDocumentAnalysis.cashout_upload_id == upload_id)
    )
    return (await db.execute(stmt)).scalar_one()


async def add_analysis(db: AsyncSession, analysis: CashoutDocumentAnalysis) -> None:
    db.add(analysis)
    await db.flush()


async def delete_analyses(
    db: AsyncSession, analyses: Iterable[CashoutDocumentAnalysis]
) -> None:
    for analysis in analyses:
        await db.delete(analysis)
    # Flushed so the rows are gone before a replacement takes their position.
    await db.flush()


__all__ = [
    "get_analysis",
    "list_analyses_for_upload",
    "count_analyses",
    "add_analysis",
    "delete_analyses",
    "get_upload",
    "get_live_submission",
]
