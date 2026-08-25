# backend/app/features/cashout/repository.py

"""Database access for the cashout feature; only its service imports this."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from .models import (
    CashoutData,
    CashoutDocument,
    CashoutDocumentAnalysis,
    CashoutSubmission,
)

# ================================
# --------- Submissions ----------
# ================================

# Soft-deleted submissions (deleted_at set) behave as gone: every submission
# lookup excludes them, which also strands their documents and analyses —
# each service path resolves the submission first and now finds nothing.


async def add_submission(db: AsyncSession, submission: CashoutSubmission) -> None:
    db.add(submission)
    await db.flush()


async def get_submission(
    db: AsyncSession, *, submission_id: UUID
) -> CashoutSubmission | None:
    stmt = select(CashoutSubmission).where(
        CashoutSubmission.id == submission_id,
        CashoutSubmission.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_submission_with_details(
    db: AsyncSession, *, submission_id: UUID
) -> CashoutSubmission | None:
    stmt = (
        select(CashoutSubmission)
        .options(
            selectinload(CashoutSubmission.documents).joinedload(
                CashoutDocument.analysis
            ),
            joinedload(CashoutSubmission.data),
            joinedload(CashoutSubmission.employee),
        )
        .where(
            CashoutSubmission.id == submission_id,
            CashoutSubmission.deleted_at.is_(None),
        )
    )

    return (await db.execute(stmt)).scalar_one_or_none()


async def list_submissions(
    db: AsyncSession, *, only_user_id: UUID | None
) -> Sequence[CashoutSubmission]:
    stmt = (
        select(CashoutSubmission)
        .options(joinedload(CashoutSubmission.employee))
        .where(CashoutSubmission.deleted_at.is_(None))
        .order_by(CashoutSubmission.submitted_at.desc())
    )
    if only_user_id is not None:
        stmt = stmt.where(CashoutSubmission.employee_user_id == only_user_id)

    return (await db.execute(stmt)).scalars().all()


async def delete_submission(db: AsyncSession, submission: CashoutSubmission) -> None:
    await db.delete(submission)
    # Surface the cashout_data ON DELETE RESTRICT violation before removing
    # document objects or returning a successful response.
    await db.flush()


# ================================
# ---------- Documents -----------
# ================================


async def get_document(
    db: AsyncSession, *, document_id: UUID
) -> CashoutDocument | None:
    return await db.get(CashoutDocument, document_id)


async def list_storage_keys(db: AsyncSession, *, submission_id: UUID) -> list[str]:
    return list(
        await db.scalars(
            select(CashoutDocument.storage_key).where(
                CashoutDocument.cashout_submission_id == submission_id
            )
        )
    )


async def list_documents_with_analysis(
    db: AsyncSession, *, submission_id: UUID
) -> Sequence[CashoutDocument]:
    stmt = (
        select(CashoutDocument)
        .options(joinedload(CashoutDocument.analysis))
        .where(CashoutDocument.cashout_submission_id == submission_id)
    )
    return (await db.execute(stmt)).scalars().all()


async def add_document(db: AsyncSession, document: CashoutDocument) -> None:
    # Flush before writing to storage: the (submission, checksum) unique index
    # rejects a duplicate upload before its bytes land in the object store.
    db.add(document)
    await db.flush()


async def delete_document(db: AsyncSession, document: CashoutDocument) -> None:
    await db.delete(document)
    # Flush so a database failure surfaces before the stored bytes are gone.
    await db.flush()


# ================================
# ---------- Analyses ------------
# ================================


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


# ================================
# ------------- Data -------------
# ================================


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
    "add_submission",
    "get_submission",
    "get_submission_with_details",
    "list_submissions",
    "delete_submission",
    "get_document",
    "list_storage_keys",
    "list_documents_with_analysis",
    "add_document",
    "delete_document",
    "get_analysis",
    "find_analysis_by_document",
    "add_analysis",
    "add_data",
    "find_data_by_submission",
    "delete_data",
    "list_data",
]
