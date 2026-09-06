# backend/app/features/cashout/documents/repository.py

"""Database access for cashout documents; only the documents service imports this."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Sibling reads: the live-submission walk-up read comes from the owning
# repository (which states the soft-delete contract) instead of restating the
# query, and the crop roll-up below selects the sibling analysis model; writes
# stay in the owning repository.
from app.features.cashout.analyses.model import CashoutDocumentAnalysis
from app.features.cashout.submissions.repository import (
    get_submission as get_live_submission,
)

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


async def list_crop_storage_keys(db: AsyncSession, *, document_id: UUID) -> list[str]:
    """The stored crops the document's analyses read (see analyses.model):
    objects that go with the document, and that the cascade alone would
    strand in storage."""
    keys = await db.scalars(
        select(CashoutDocumentAnalysis.cropped_storage_key).where(
            CashoutDocumentAnalysis.cashout_document_id == document_id,
            CashoutDocumentAnalysis.cropped_storage_key.is_not(None),
        )
    )
    return [key for key in keys if key is not None]


__all__ = [
    "get_document",
    "add_document",
    "delete_document",
    "list_crop_storage_keys",
    "get_live_submission",
]
