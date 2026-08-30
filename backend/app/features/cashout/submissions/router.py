# backend/app/features/cashout/submissions/router.py

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status

from app.errors import error_responses
from app.features.auth.dependencies import get_current_user, require_admin
from app.features.users.model import User
from app.infrastructure.db.dependencies import DbSession
from app.integrations.storage import DocumentStorageClient
from app.integrations.storage.dependencies import get_document_storage

from . import service as submissions_service
from .schemas import (
    CashoutSubmissionComplete,
    CashoutSubmissionCreate,
    CashoutSubmissionDetailOut,
    CashoutSubmissionListOut,
    CashoutSubmissionOut,
)

router = APIRouter()

# Path parameters are UUIDs; Pydantic validates them (a malformed id → 422).
SubmissionId = Annotated[UUID, Path(description="Cashout submission ID.")]


@router.post(
    "/submissions",
    response_model=CashoutSubmissionOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses("SUBMISSION_DUPLICATE_DAY", "VALIDATION_FAILED"),
)
async def create_submission(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    # The body is optional: a bare POST opens a cashout for today.
    payload: CashoutSubmissionCreate | None = None,
) -> CashoutSubmissionOut:
    """Open a new cashout submission (status `PROCESSING`).

    Cashouts are not shift-locked; a cashier may open one at any time — but
    only one live cashout per business day, so opening a second for a day
    that already has one conflicts. The optional `businessDate` is the day
    the cashout is for — yesterday, for a close-out after midnight or a
    missed day — and defaults to today.
    """
    submission = await submissions_service.create_submission(
        db,
        user_id=current_user.id,
        business_date=payload.business_date if payload is not None else None,
    )
    return CashoutSubmissionOut.model_validate(submission)


@router.delete(
    "/submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        "SUBMISSION_NOT_FOUND", "SUBMISSION_COMPLETED", "VALIDATION_FAILED"
    ),
)
async def delete_submission(
    submission_id: SubmissionId,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> None:
    """Delete an incomplete submission; a completed one cannot be deleted.

    The submission's employee or an admin may cancel it. A submission with
    no traces (no documents, no data, never completed) is removed outright;
    anything else is soft-deleted and simply disappears from the API.
    """
    await submissions_service.delete_submission(
        db,
        submission_id=submission_id,
        user=current_user,
        storage=storage,
    )


@router.get("/submissions", response_model=list[CashoutSubmissionListOut])
async def list_submissions(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[CashoutSubmissionListOut]:
    """List submissions, newest first, with the submitting user.

    Cashiers see their own submissions; admins see everyone's.
    """
    submissions = await submissions_service.list_submissions(db, user=current_user)
    return [CashoutSubmissionListOut.model_validate(s) for s in submissions]


@router.get(
    "/submissions/{submission_id}",
    response_model=CashoutSubmissionDetailOut,
    responses=error_responses("SUBMISSION_NOT_FOUND", "VALIDATION_FAILED"),
)
async def get_submission(
    submission_id: SubmissionId,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutSubmissionDetailOut:
    """Return a submission with its documents (analyses included) and data.

    Accessible to the submission's employee or an admin.
    """
    submission = await submissions_service.get_submission(
        db, submission_id=submission_id, user=current_user
    )
    return CashoutSubmissionDetailOut.model_validate(submission)


@router.post(
    "/submissions/{submission_id}/complete",
    response_model=CashoutSubmissionOut,
    responses=error_responses(
        "SUBMISSION_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "SUBMISSION_EMPTY",
        "SUBMISSION_UNVERIFIED",
        "RECONCILE_TOUCHBISTRO_MISSING",
        "RECONCILE_TOUCHBISTRO_DUPLICATE",
        "RECONCILE_CARD_PAYMENT_MISMATCH",
        "RECONCILE_CARD_TRANSACTION_MISMATCH",
        "RECONCILE_DOCUMENT_DATA_INVALID",
        "VALIDATION_FAILED",
    ),
)
async def complete_submission(
    submission_id: SubmissionId,
    payload: CashoutSubmissionComplete,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutSubmissionOut:
    """Close out the cashout once every document analysis is verified.

    Reconciles the verified analyses into the submission's cashout data and
    moves the submission to `COMPLETED`. The submission's employee or an
    admin may complete it; the completing user is recorded.

    Reconciliation is also where the cashout's documents are cross-checked:
    it takes exactly one TouchBistro report, and the server summaries filed
    with it must add up to that report's card payments and card orders. A
    cashout that does not add up stays open with a `RECONCILE_*` conflict.
    """
    submission = await submissions_service.complete_submission(
        db, payload=payload, submission_id=submission_id, user=current_user
    )
    return CashoutSubmissionOut.model_validate(submission)


@router.post(
    "/submissions/{submission_id}/unsubmit",
    response_model=CashoutSubmissionOut,
    dependencies=[Depends(require_admin)],
    responses=error_responses(
        "SUBMISSION_NOT_FOUND", "SUBMISSION_NOT_COMPLETED", "VALIDATION_FAILED"
    ),
)
async def unsubmit_submission(
    submission_id: SubmissionId,
    db: DbSession,
) -> CashoutSubmissionOut:
    """Reopen a completed cashout for editing (admin only).

    Removes the reconciled cashout data and moves the submission back to
    `PROCESSING`, clearing who currently completed it — the employee can edit
    it again. The document analyses stay verified, so completing the cashout
    again regenerates the data from them.
    """
    submission = await submissions_service.unsubmit_submission(
        db, submission_id=submission_id
    )
    return CashoutSubmissionOut.model_validate(submission)


__all__ = ["router"]
