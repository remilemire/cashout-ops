# backend/app/features/cashout/analyses/repository.py

"""Database access for cashout analyses; only the analyses service imports this."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cashout.documents.model import CashoutDocument
from app.features.cashout.submissions.model import CashoutSubmission

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


# Walk-up reads over sibling models (the document, then its live submission).
# These stay separate queries so each NOT_FOUND error surfaces at the same
# step as before; do not merge them into one joined query.


async def get_document(
    db: AsyncSession, *, document_id: UUID
) -> CashoutDocument | None:
    # Same read as documents/repository.py's get_document.
    return await db.get(CashoutDocument, document_id)


async def get_live_submission(
    db: AsyncSession, *, submission_id: UUID
) -> CashoutSubmission | None:
    # Walk-up read; the soft-delete contract lives in submissions/repository.py.
    stmt = select(CashoutSubmission).where(
        CashoutSubmission.id == submission_id,
        CashoutSubmission.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


__all__ = [
    "get_analysis",
    "find_analysis_by_document",
    "add_analysis",
    "get_document",
    "get_live_submission",
]
