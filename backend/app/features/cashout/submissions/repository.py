# backend/app/features/cashout/submissions/repository.py

"""Database access for cashout submissions; only the submissions service imports this."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.features.cashout.documents.model import CashoutDocument

from .model import CashoutSubmission

# Soft-deleted submissions (deleted_at set) behave as gone: every submission
# lookup excludes them, which also strands their documents and analyses —
# each service path resolves the submission first and now finds nothing.
# This is the canonical statement of the contract; the sibling repositories
# re-export get_submission (as get_live_submission) rather than restating the
# predicate.


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


# Roll-up reads over the sibling CashoutDocument model, which submission
# lifecycle operations need. Reads may cross sub-features; writes stay in the
# owning repository.


async def list_storage_keys(db: AsyncSession, *, submission_id: UUID) -> list[str]:
    """Every stored object behind the submission's documents: each original
    and, where the upload was cropped, its crop."""
    rows = await db.execute(
        select(CashoutDocument.storage_key, CashoutDocument.cropped_storage_key).where(
            CashoutDocument.cashout_submission_id == submission_id
        )
    )
    return [key for original, cropped in rows for key in (original, cropped) if key]


async def list_documents_with_analysis(
    db: AsyncSession, *, submission_id: UUID
) -> Sequence[CashoutDocument]:
    stmt = (
        select(CashoutDocument)
        .options(joinedload(CashoutDocument.analysis))
        .where(CashoutDocument.cashout_submission_id == submission_id)
    )
    return (await db.execute(stmt)).scalars().all()


__all__ = [
    "add_submission",
    "get_submission",
    "get_submission_with_details",
    "list_submissions",
    "delete_submission",
    "list_storage_keys",
    "list_documents_with_analysis",
]
