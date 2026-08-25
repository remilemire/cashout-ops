# backend/app/features/cashout/documents/repository.py

"""Database access for cashout documents; only the documents service imports this."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cashout.submissions.model import CashoutSubmission

from .model import CashoutDocument


async def get_document(
    db: AsyncSession, *, document_id: UUID
) -> CashoutDocument | None:
    return await db.get(CashoutDocument, document_id)


async def add_document(db: AsyncSession, document: CashoutDocument) -> None:
    # Flush before writing to storage: the (submission, checksum) unique index
    # rejects a duplicate upload before its bytes land in the object store.
    db.add(document)
    await db.flush()


async def delete_document(db: AsyncSession, document: CashoutDocument) -> None:
    await db.delete(document)
    # Flush so a database failure surfaces before the stored bytes are gone.
    await db.flush()


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
    "get_document",
    "add_document",
    "delete_document",
    "get_live_submission",
]
