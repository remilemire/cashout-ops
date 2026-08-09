# backend/app/features/cashout/router.py

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.errors.openapi import error_responses
from app.features.auth.dependencies import (
    get_current_user,
    require_admin,
    require_verified_user,
)
from app.features.users.model import User
from app.infrastructure.db.dependencies import get_db
from app.integrations.storage import DocumentStorageClient
from app.integrations.storage.dependencies import get_document_storage
from app.lib.documents import DocumentContentType
from app.security.dependencies import require_csrf

from . import service as cashout_service
from .extraction import CashoutDocumentProcessor
from .extraction.dependencies import get_cashout_document_processor
from .schemas import (
    CashoutAnalysisVerify,
    CashoutDataOut,
    CashoutDocumentAnalysisOut,
    CashoutSubmissionDetailOut,
    CashoutSubmissionListOut,
    CashoutSubmissionOut,
)
from .types import DocumentUpload

router = APIRouter(
    prefix="/cashout",
    tags=["cashout"],
    dependencies=[
        Depends(require_csrf),
        Depends(get_current_user),
        Depends(require_verified_user),
    ],
    responses=error_responses(
        "UNAUTHENTICATED",
        "INVALID_SESSION",
        "INVALID_CSRF_TOKEN",
        "FORBIDDEN",
        "EMAIL_NOT_VERIFIED",
    ),
)

# Path parameters are UUIDs; Pydantic validates them (a malformed id → 422).
SubmissionId = Annotated[UUID, Path(description="Cashout submission ID.")]
DocumentId = Annotated[UUID, Path(description="Cashout document ID.")]
AnalysisId = Annotated[UUID, Path(description="Cashout document analysis ID.")]


# ================================
# --------- Submissions ----------
# ================================


@router.post(
    "/submissions",
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
    submission = await cashout_service.create_submission(db, user_id=current_user.id)
    return CashoutSubmissionOut.model_validate(submission)


@router.delete(
    "/submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        "SUBMISSION_NOT_FOUND", "SUBMISSION_HAS_DATA", "VALIDATION_FAILED"
    ),
)
async def delete_submission(
    submission_id: SubmissionId,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> None:
    """Delete an owned submission that has no reconciled cashout data."""
    await cashout_service.delete_submission(
        db,
        submission_id=submission_id,
        user_id=current_user.id,
        storage=storage,
    )


@router.get("/submissions", response_model=list[CashoutSubmissionListOut])
async def list_submissions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[CashoutSubmissionListOut]:
    """List submissions, newest first, with the submitting user.

    Cashiers see their own submissions; admins see everyone's.
    """
    submissions = await cashout_service.list_submissions(db, user=current_user)
    return [CashoutSubmissionListOut.model_validate(s) for s in submissions]


@router.get(
    "/submissions/{submission_id}",
    response_model=CashoutSubmissionDetailOut,
    responses=error_responses("SUBMISSION_NOT_FOUND", "VALIDATION_FAILED"),
)
async def get_submission(
    submission_id: SubmissionId,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutSubmissionDetailOut:
    """Return a submission with its documents (analyses included) and data.

    Accessible to the submission's owner or an admin.
    """
    submission = await cashout_service.get_submission(
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
    moves the submission to `COMPLETED`.
    """
    submission = await cashout_service.complete_submission(
        db, submission_id=submission_id, user_id=current_user.id
    )
    return CashoutSubmissionOut.model_validate(submission)


# ================================
# ---------- Documents -----------
# ================================


@router.post(
    "/submissions/{submission_id}/documents",
    response_model=CashoutDocumentAnalysisOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(
        "UNSUPPORTED_DOCUMENT_TYPE",
        "DOCUMENT_TOO_LARGE",
        "DOCUMENT_DUPLICATE",
        "SUBMISSION_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "VALIDATION_FAILED",
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

    Accepts JPEG, PNG, WebP, or PDF up to 20 MB; a file already uploaded to
    this submission (same checksum) is rejected. The AI extraction runs in the
    background: this returns the analysis in `EXTRACTING`; poll
    `GET /cashout/analyses/{id}` until it reaches `NEEDS_VERIFICATION` or
    `FAILED` (retry via the extract endpoint).
    """
    payload = DocumentUpload(
        data=await file.read(),
        content_type=_to_content_type(file.content_type),
        original_filename=file.filename or "upload",
    )
    analysis = await cashout_service.upload_document(
        db,
        payload=payload,
        submission_id=submission_id,
        user_id=current_user.id,
        storage=storage,
        processor=processor,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        "DOCUMENT_NOT_FOUND", "SUBMISSION_COMPLETED", "VALIDATION_FAILED"
    ),
)
async def delete_document(
    document_id: DocumentId,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> None:
    """Remove a document (and its analysis) from an incomplete submission.

    Only the submission's owner may remove documents, and only while the
    submission is still `PROCESSING`.
    """
    await cashout_service.delete_document(
        db,
        document_id=document_id,
        user_id=current_user.id,
        storage=storage,
    )


@router.post(
    "/documents/{document_id}/extract",
    response_model=CashoutDocumentAnalysisOut,
    responses=error_responses(
        "DOCUMENT_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "ANALYSIS_VERIFIED",
        "EXTRACTION_IN_PROGRESS",
        "VALIDATION_FAILED",
    ),
)
async def extract_document(
    document_id: DocumentId,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    processor: Annotated[
        CashoutDocumentProcessor, Depends(get_cashout_document_processor)
    ],
) -> CashoutDocumentAnalysisOut:
    """Restart extraction on a document (e.g. after a `FAILED` attempt).

    Resets the analysis to `EXTRACTING` and runs the AI in the background —
    poll `GET /cashout/analyses/{id}` for the outcome. A verified analysis
    cannot be re-run, nor one whose extraction is still in progress.
    """
    analysis = await cashout_service.extract_document(
        db,
        document_id=document_id,
        user_id=current_user.id,
        processor=processor,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


_DOCUMENT_CONTENT_OK: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The original uploaded bytes.",
        "content": {member.value: {} for member in DocumentContentType},
    }
}


@router.get(
    "/documents/{document_id}/content",
    response_class=Response,
    responses=_DOCUMENT_CONTENT_OK
    | error_responses("DOCUMENT_NOT_FOUND", "VALIDATION_FAILED"),
)
async def get_document_content(
    document_id: DocumentId,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> Response:
    """Serve the original uploaded document (image or PDF), inline.

    Accessible to the submission's owner or an admin.
    """
    document, data = await cashout_service.get_document_content(
        db, document_id=document_id, user=current_user, storage=storage
    )
    filename = document.original_filename.replace('"', "")
    return Response(
        content=data,
        media_type=document.content_type.value,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ================================
# ---------- Analyses ------------
# ================================


@router.get(
    "/analyses/{analysis_id}",
    response_model=CashoutDocumentAnalysisOut,
    responses=error_responses("ANALYSIS_NOT_FOUND", "VALIDATION_FAILED"),
)
async def get_analysis(
    analysis_id: AnalysisId,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutDocumentAnalysisOut:
    """Poll a document analysis for its extraction progress.

    `EXTRACTING` means the AI is still running; it resolves to
    `NEEDS_VERIFICATION` or `FAILED`. Accessible to the submission's owner or
    an admin.
    """
    analysis = await cashout_service.get_analysis(
        db, analysis_id=analysis_id, user=current_user
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


@router.post(
    "/analyses/{analysis_id}/verify",
    response_model=CashoutDocumentAnalysisOut,
    responses=error_responses(
        "ANALYSIS_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "ANALYSIS_VERIFIED",
        "EXTRACTION_IN_PROGRESS",
        "EXTRACTION_FAILED",
        "VALIDATION_FAILED",
    ),
)
async def verify_analysis(
    analysis_id: AnalysisId,
    payload: CashoutAnalysisVerify,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutDocumentAnalysisOut:
    """Confirm an extraction, optionally submitting corrected values.

    Marks the analysis `VERIFIED`. `verifiedData` overrides the extracted data;
    omit it to confirm the extraction as-is.
    """
    analysis = await cashout_service.verify_analysis(
        db, payload=payload, analysis_id=analysis_id, user_id=current_user.id
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


# ================================
# ------------- Data -------------
# ================================


@router.get(
    "/data",
    response_model=list[CashoutDataOut],
    dependencies=[Depends(require_admin)],
)
async def list_data(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CashoutDataOut]:
    """List every reconciled cashout data row, newest first (admin only)."""
    data = await cashout_service.list_data(db)
    return [CashoutDataOut.model_validate(row) for row in data]


def _to_content_type(content_type: str | None) -> DocumentContentType:
    try:
        return DocumentContentType(content_type or "")
    except ValueError:
        raise AppError(
            "UNSUPPORTED_DOCUMENT_TYPE",
            f"Unsupported document content type: {content_type!r}.",
        ) from None
