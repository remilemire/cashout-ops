# backend/app/features/cashout/submissions/repository.py

"""Database access for cashout submissions; only the submissions service imports this."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.features.cashout.analyses.model import CashoutDocumentAnalysis
from app.features.cashout.uploads.model import CashoutUpload

from .model import CashoutSubmission

# Soft-deleted submissions (deleted_at set) behave as gone: every submission
# lookup excludes them, which also strands their uploads and analyses —
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
            selectinload(CashoutSubmission.uploads).selectinload(
                CashoutUpload.analyses
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
    # stored objects or returning a successful response.
    await db.flush()


# Roll-up reads over the sibling CashoutUpload model, which submission
# lifecycle operations need. Reads may cross sub-features; writes stay in the
# owning repository.


async def list_storage_keys(db: AsyncSession, *, submission_id: UUID) -> list[str]:
    """Every stored object behind the submission's uploads: each original,
    and the crop each of their analyses read (see analyses.model)."""
    originals = await db.scalars(
        select(CashoutUpload.storage_key).where(
            CashoutUpload.cashout_submission_id == submission_id
        )
    )
    crops = await db.scalars(
        select(CashoutDocumentAnalysis.cropped_storage_key)
        .join(
            CashoutUpload,
            CashoutDocumentAnalysis.cashout_upload_id == CashoutUpload.id,
        )
        .where(
            CashoutUpload.cashout_submission_id == submission_id,
            CashoutDocumentAnalysis.cropped_storage_key.is_not(None),
        )
    )
    return [*originals, *(key for key in crops if key is not None)]


async def list_uploads_with_analyses(
    db: AsyncSession, *, submission_id: UUID
) -> Sequence[CashoutUpload]:
    stmt = (
        select(CashoutUpload)
        .options(selectinload(CashoutUpload.analyses))
        .where(CashoutUpload.cashout_submission_id == submission_id)
    )
    return (await db.execute(stmt)).scalars().all()


__all__ = [
    "add_submission",
    "get_submission",
    "get_submission_with_details",
    "list_submissions",
    "delete_submission",
    "list_storage_keys",
    "list_uploads_with_analyses",
]
