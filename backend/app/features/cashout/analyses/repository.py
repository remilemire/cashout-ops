# backend/app/features/cashout/analyses/repository.py

"""Database access for cashout analyses; only the analyses service imports this."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Sibling read reuse: the walk-up reads (the document, then its live submission)
# come from the owning repositories instead of restating their queries. The
# service still runs them as separate calls so each NOT_FOUND error surfaces at
# the same step as before; writes stay in the owning repository.
from app.features.cashout.documents.repository import get_document
from app.features.cashout.submissions.repository import (
    get_submission as get_live_submission,
)

from .model import CashoutDocumentAnalysis


async def get_analysis(
    db: AsyncSession, *, analysis_id: UUID
) -> CashoutDocumentAnalysis | None:
    return await db.get(CashoutDocumentAnalysis, analysis_id)


async def find_analysis_by_document(
    db: AsyncSession, *, document_id: UUID
) -> CashoutDocumentAnalysis | None:
    stmt = select(CashoutDocumentAnalysis).where(
        CashoutDocumentAnalysis.cashout_document_id == document_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def add_analysis(db: AsyncSession, analysis: CashoutDocumentAnalysis) -> None:
    db.add(analysis)
    await db.flush()


__all__ = [
    "get_analysis",
    "find_analysis_by_document",
    "add_analysis",
    "get_document",
    "get_live_submission",
]
