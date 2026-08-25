# backend/app/features/cashout/submissions/router.py

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError, error_responses
from app.features.auth.dependencies import get_current_user, require_admin
from app.features.cashout.analyses.schemas import CashoutDocumentAnalysisOut
from app.features.cashout.documents.types import DocumentUpload
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.features.cashout.extraction.dependencies import (
    get_cashout_document_processor,
)
from app.features.cashout.shared import intake
from app.features.users.model import User
from app.infrastructure.db.dependencies import get_db
from app.integrations.storage import DocumentStorageClient
from app.integrations.storage.dependencies import get_document_storage
from app.lib.documents import DocumentContentType, read_document

from . import service as submissions_service
from .dependencies import rate_limit_upload
from .schemas import (
    CashoutSubmissionDetailOut,
    CashoutSubmissionListOut,
    CashoutSubmissionOut,
)

router = APIRouter(prefix="/submissions")

# Path parameters are UUIDs; Pydantic validates them (a malformed id → 422).
SubmissionId = Annotated[UUID, Path(description="Cashout submission ID.")]


@router.post(
    "",
    response_model=CashoutSubmissionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_submission(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutSubmissionOut:
    """Open a new cashout submission (status `PROCESSING`).

    Cashouts are not shift-locked; a cashier may open one at any time.
    """
    submission = await submissions_service.create_submission(
        db, user_id=current_user.id
    )
    return CashoutSubmissionOut.model_validate(submission)


@router.delete(
    "/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        "SUBMISSION_NOT_FOUND", "SUBMISSION_COMPLETED", "VALIDATION_FAILED"
    ),
)
async def delete_submission(
    submission_id: SubmissionId,
    db: Annotated[AsyncSession, Depends(get_db)],
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


@router.get("", response_model=list[CashoutSubmissionListOut])
async def list_submissions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[CashoutSubmissionListOut]:
    """List submissions, newest first, with the submitting user.

    Cashiers see their own submissions; admins see everyone's.
    """
    submissions = await submissions_service.list_submissions(db, user=current_user)
    return [CashoutSubmissionListOut.model_validate(s) for s in submissions]


@router.get(
    "/{submission_id}",
    response_model=CashoutSubmissionDetailOut,
    responses=error_responses("SUBMISSION_NOT_FOUND", "VALIDATION_FAILED"),
)
async def get_submission(
    submission_id: SubmissionId,
    db: Annotated[AsyncSession, Depends(get_db)],
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
    "/{submission_id}/complete",
    response_model=CashoutSubmissionOut,
    responses=error_responses(
        "SUBMISSION_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "SUBMISSION_EMPTY",
        "SUBMISSION_UNVERIFIED",
        "VALIDATION_FAILED",
    ),
)
async def complete_submission(
    submission_id: SubmissionId,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutSubmissionOut:
    """Close out the cashout once every document analysis is verified.

    Reconciles the verified analyses into the submission's cashout data and
    moves the submission to `COMPLETED`. The submission's employee or an
    admin may complete it; the completing user is recorded.
    """
    submission = await submissions_service.complete_submission(
        db, submission_id=submission_id, user=current_user
    )
    return CashoutSubmissionOut.model_validate(submission)


@router.post(
    "/{submission_id}/unsubmit",
    response_model=CashoutSubmissionOut,
    dependencies=[Depends(require_admin)],
    responses=error_responses(
        "SUBMISSION_NOT_FOUND", "SUBMISSION_NOT_COMPLETED", "VALIDATION_FAILED"
    ),
)
async def unsubmit_submission(
    submission_id: SubmissionId,
    db: Annotated[AsyncSession, Depends(get_db)],
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


# The URL addresses a submission; the behavior spans sub-features (shared/intake.py).
@router.post(
    "/{submission_id}/documents",
    response_model=CashoutDocumentAnalysisOut,
    status_code=status.HTTP_201_CREATED,
    # Each upload starts an AI extraction, so it draws on the per-user quota.
    dependencies=[Depends(rate_limit_upload)],
    responses=error_responses(
        "UNSUPPORTED_DOCUMENT_TYPE",
        "DOCUMENT_TOO_LARGE",
        "DOCUMENT_DUPLICATE",
        "SUBMISSION_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "VALIDATION_FAILED",
        "RATE_LIMITED",
    ),
)
async def upload_document(
    submission_id: SubmissionId,
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
    processor: Annotated[
        CashoutDocumentProcessor, Depends(get_cashout_document_processor)
    ],
) -> CashoutDocumentAnalysisOut:
    """Upload an end-of-shift document and start its extraction.

    Accepts JPEG, PNG, WebP, or PDF within the configured size limit
    (`STORAGE_MAX_DOCUMENT_SIZE_MB`); a file already uploaded to this submission (same
    checksum) is rejected. The AI extraction runs in the background: this
    returns the analysis in `EXTRACTING`; poll `GET /cashout/analyses/{id}`
    until it reaches `NEEDS_VERIFICATION` or `FAILED` (retry via the extract
    endpoint).

    The content type is checked before the body is read, and the body itself is
    read only up to the limit (plus the byte that proves it was exceeded); the
    service rejects it from there.
    """
    # Resolved first so an unsupported type is rejected without reading the
    # document: keyword arguments evaluate in order, so this cannot be inlined
    # below `data` without reading the body of a file we are about to refuse.
    content_type = _to_content_type(file.content_type)
    payload = DocumentUpload(
        data=await read_document(file, limit=settings.storage.MAX_DOCUMENT_SIZE_BYTES),
        content_type=content_type,
        original_filename=file.filename or "upload",
    )
    analysis = await intake.upload_document(
        db,
        payload=payload,
        submission_id=submission_id,
        user=current_user,
        storage=storage,
        processor=processor,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


def _to_content_type(content_type: str | None) -> DocumentContentType:
    try:
        return DocumentContentType(content_type or "")
    except ValueError:
        raise AppError(
            "UNSUPPORTED_DOCUMENT_TYPE",
            f"Unsupported document content type: {content_type!r}.",
        ) from None


__all__ = ["router"]
