# backend/app/features/cashout/uploads/repository.py

"""Database access for cashout uploads; only the uploads service imports this."""

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

from .model import CashoutUpload


async def get_upload(db: AsyncSession, *, upload_id: UUID) -> CashoutUpload | None:
    return await db.get(CashoutUpload, upload_id)


async def add_upload(db: AsyncSession, upload: CashoutUpload) -> None:
    # Flush before writing to storage: the (submission, checksum) unique index
    # rejects a duplicate upload before its bytes land in the object store.
    db.add(upload)
    await db.flush()


async def delete_upload(db: AsyncSession, upload: CashoutUpload) -> None:
    await db.delete(upload)
    # Flush so a database failure surfaces before the stored bytes are gone.
    await db.flush()


async def list_crop_storage_keys(db: AsyncSession, *, upload_id: UUID) -> list[str]:
    """The storage keys of the crops recorded on the upload's analyses.

    Deleting the upload cascades to its analysis rows, not to the objects
    they point at, so the caller deletes these from storage itself.
    """
    keys = await db.scalars(
        select(CashoutDocumentAnalysis.cropped_storage_key).where(
            CashoutDocumentAnalysis.cashout_upload_id == upload_id,
            CashoutDocumentAnalysis.cropped_storage_key.is_not(None),
        )
    )
    return [key for key in keys if key is not None]


__all__ = [
    "get_upload",
    "add_upload",
    "delete_upload",
    "list_crop_storage_keys",
    "get_live_submission",
]
