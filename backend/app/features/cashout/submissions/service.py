# backend/app/features/cashout/submissions/service.py

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.features.cashout.analyses.model import CashoutDocumentAnalysis
from app.features.cashout.analyses.types import DocumentAnalysisStatus
from app.features.cashout.data import service as data_service
from app.features.cashout.shared.access import ensure_can_view, is_admin
from app.features.users.model import User
from app.integrations.storage import DocumentStorageClient

from . import repository
from .model import CashoutSubmission
from .schemas import CashoutSubmissionComplete, CashoutSubmissionUpdate
from .types import CashoutSubmissionStatus


async def create_submission(
    db: AsyncSession, *, user_id: UUID, business_date: date | None = None
) -> CashoutSubmission:
    # Cashouts are not shift-locked; a user may open one at any time — but at
    # most one live cashout per business day: the partial unique index on
    # (employee_user_id, business_date) rejects a duplicate at the flush
    # below, and the integrity translator turns it into
    # SUBMISSION_DUPLICATE_DAY. The creator is the cashout's employee.
    #
    # The client normally supplies business_date: the cashier's local date is
    # the restaurant's day, and the server's timezone need not match it. The
    # server-side today is only a fallback for bodyless API calls.
    submission = CashoutSubmission(
        employee_user_id=user_id,
        submitted_at=datetime.now(UTC),
        business_date=business_date if business_date is not None else date.today(),
    )
    await repository.add_submission(db, submission)

    return submission


async def update_submission(
    db: AsyncSession,
    *,
    payload: CashoutSubmissionUpdate,
    submission_id: UUID,
    user: User,
) -> CashoutSubmission:
    """Move a cashout to another business day.

    Editable for as long as the cashout is PROCESSING — an unsubmit reopens
    it — by its employee or an admin. At most one live cashout per employee
    per day still holds: the partial unique index rejects an occupied day
    when the request's transaction commits, and the integrity translator
    turns it into SUBMISSION_DUPLICATE_DAY (the session is function-scoped,
    so that commit still answers the request). Re-saving the same day is a
    no-op.
    """
    submission = await _get_submission_for_actor(
        db, submission_id=submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED",
            "A completed cashout's business date cannot be changed.",
        )

    submission.business_date = payload.business_date

    return submission


async def delete_submission(
    db: AsyncSession,
    *,
    submission_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> None:
    """Delete a submission (employee or admin); a completed one never can be.

    A PROCESSING submission with no traces at all — no uploads, no
    reconciled data, never completed — is removed outright. Anything else is
    soft-deleted (deleted_at stamped): the row, its uploads, analyses, and
    stored files survive, but every lookup excludes it.
    """
    submission = await _get_submission_for_actor(
        db, submission_id=submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError("SUBMISSION_COMPLETED", "A completed cashout cannot be deleted.")

    # The reconciled data is fully derived from the submission, so it goes
    # with it — either path. In practice unsubmit already removed it (that is
    # the only way a PROCESSING submission relates to a data row); the
    # RESTRICT FK stays as the safety net should a future path forget.
    data = await data_service.delete_for_submission(db, submission_id=submission.id)

    storage_keys = await repository.list_storage_keys(db, submission_id=submission.id)
    has_traces = (
        bool(storage_keys)  # at least one key per upload
        or data is not None
        or submission.first_completed_at is not None
    )
    if has_traces:
        submission.deleted_at = datetime.now(UTC)
        return

    await repository.delete_submission(db, submission)

    # Vacuously empty here (no traces means no uploads), kept so a future
    # hard-delete path cannot leak stored files.
    for storage_key in storage_keys:
        await storage.delete(storage_key)


async def get_submission(
    db: AsyncSession, *, submission_id: UUID, user: User
) -> CashoutSubmission:
    submission = await repository.get_submission_with_details(
        db, submission_id=submission_id
    )
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND")

    ensure_can_view(submission, user)

    return submission


async def list_submissions(
    db: AsyncSession, *, user: User
) -> Sequence[CashoutSubmission]:
    """Admins (and the owner) see every submission; cashiers only their own.
    Newest first."""
    only_user_id = None if is_admin(user) else user.id
    return await repository.list_submissions(db, only_user_id=only_user_id)


async def complete_submission(
    db: AsyncSession,
    *,
    payload: CashoutSubmissionComplete,
    submission_id: UUID,
    user: User,
) -> CashoutSubmission:
    """Reconcile the verified analyses into a CashoutData and close the cashout."""
    submission = await _get_submission_for_actor(
        db, submission_id=submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError("SUBMISSION_COMPLETED")

    uploads = await repository.list_uploads_with_analyses(
        db, submission_id=submission.id
    )
    if not uploads:
        raise AppError("SUBMISSION_EMPTY")

    # Every analysis of every upload — each document found in an upload
    # is verified on its own — and no upload without one.
    analyses: list[CashoutDocumentAnalysis] = []
    for upload in uploads:
        if not upload.analyses:
            raise AppError("SUBMISSION_UNVERIFIED")
        for analysis in upload.analyses:
            if analysis.status is not DocumentAnalysisStatus.VERIFIED:
                raise AppError("SUBMISSION_UNVERIFIED")
            analyses.append(analysis)

    data = await data_service.reconcile(
        db,
        submission_id=submission.id,
        analyses=analyses,
        tipout_departments=payload.tipout_departments,
    )
    submission.status = CashoutSubmissionStatus.COMPLETED
    # Snapshot the departments the row was reconciled with (the selection
    # plus the manager, already sorted) on the submission itself, so unsubmit
    # (which drops the data row) does not lose them.
    submission.tipout_departments = list(data.tipout_departments)
    # Record the actual actor (the admin when an admin completes); the first
    # completion time is bookkeeping — set once, never overwritten.
    submission.completed_by_user_id = user.id
    if submission.first_completed_at is None:
        submission.first_completed_at = datetime.now(UTC)

    return submission


async def unsubmit_submission(
    db: AsyncSession, *, submission_id: UUID
) -> CashoutSubmission:
    """Reopen a completed cashout: drop its reconciled data, back to PROCESSING.

    Admin-only (enforced at the route). The analyses stay VERIFIED, so
    completing again reconciles them into a fresh data row.
    """
    submission = await _get_submission(db, submission_id)
    if submission.status is not CashoutSubmissionStatus.COMPLETED:
        raise AppError("SUBMISSION_NOT_COMPLETED")

    await data_service.delete_for_submission(db, submission_id=submission.id)

    submission.status = CashoutSubmissionStatus.PROCESSING
    # completed_by reflects the *current* completion, so it clears with it;
    # first_completed_at is permanent bookkeeping and survives, and so does
    # the tipout_departments snapshot — re-completion starts from the
    # previous choice.
    submission.completed_by_user_id = None

    return submission


async def _get_submission(db: AsyncSession, submission_id: UUID) -> CashoutSubmission:
    submission = await repository.get_submission(db, submission_id=submission_id)
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND")
    return submission


async def _get_submission_for_actor(
    db: AsyncSession, *, submission_id: UUID, actor: User
) -> CashoutSubmission:
    """Fetch a submission the actor may act on: its employee, or any admin.

    Admins (and the owner) have full control over every cashout, so acting
    and viewing share the same rule.
    """
    submission = await _get_submission(db, submission_id)
    ensure_can_view(submission, actor)
    return submission


__all__ = [
    "create_submission",
    "update_submission",
    "delete_submission",
    "get_submission",
    "list_submissions",
    "complete_submission",
    "unsubmit_submission",
]
