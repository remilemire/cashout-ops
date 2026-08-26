# backend/app/features/cashout/router.py

"""The flow, per document: the cashier uploads it and immediately gets back an
EXTRACTING analysis; the AI extraction runs in a background task and the
client polls the analysis until it reaches NEEDS_VERIFICATION (or FAILED,
retryable via the extract endpoint). The cashier verifies each analysis —
optionally submitting corrections. Once every document is verified,
completing the submission reconciles the analyses into a CashoutData row and
closes the cashout (COMPLETED).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError, error_responses
from app.features.auth.dependencies import get_current_user
from app.features.users.model import User
from app.infrastructure.db.dependencies import get_db
from app.integrations.storage import DocumentStorageClient
from app.integrations.storage.dependencies import get_document_storage
from app.lib.documents import DocumentContentType, read_document
from app.security.dependencies import require_csrf

from .analyses.router import router as analyses_router
from .analyses.schemas import CashoutDocumentAnalysisOut
from .data.router import router as data_router
from .dependencies import rate_limit_extract, rate_limit_upload
from .documents.router import router as documents_router
from .documents.types import DocumentUpload
from .extraction import CashoutDocumentProcessor
from .extraction.dependencies import get_cashout_document_processor
from .shared import workflows
from .submissions.router import router as submissions_router

# Every cashout route requires a session and (on unsafe methods) CSRF; the
# sub-routers inherit these along with the shared error responses.
router = APIRouter(
    prefix="/cashout",
    tags=["cashout"],
    dependencies=[
        Depends(require_csrf),
        Depends(get_current_user),
    ],
    responses=error_responses(
        "UNAUTHENTICATED",
        "INVALID_SESSION",
        "INVALID_CSRF_TOKEN",
        "FORBIDDEN",
    ),
)

# The submission lifecycle (create, list, complete, unsubmit, delete).
router.include_router(submissions_router)
# Document removal and inline viewing.
router.include_router(documents_router)
# Analysis polling and verification.
router.include_router(analyses_router)
# The reconciled cashout data (admin table).
router.include_router(data_router)

# The document workflows' HTTP entry points: these routes cross sub-feature
# URL spaces and coordinate across sub-features, so they live at the namespace
# root and call shared/workflows — mirroring auth's root logout → shared/access.

# Path parameters are UUIDs; Pydantic validates them (a malformed id → 422).
SubmissionId = Annotated[UUID, Path(description="Cashout submission ID.")]
DocumentId = Annotated[UUID, Path(description="Cashout document ID.")]


@router.post(
    "/submissions/{submission_id}/documents",
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
    analysis = await workflows.upload_document(
        db,
        payload=payload,
        submission_id=submission_id,
        user=current_user,
        storage=storage,
        processor=processor,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


@router.post(
    "/documents/{document_id}/extract",
    response_model=CashoutDocumentAnalysisOut,
    # Re-extraction burns provider tokens on demand — per-user quota applies.
    dependencies=[Depends(rate_limit_extract)],
    responses=error_responses(
        "DOCUMENT_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "ANALYSIS_VERIFIED",
        "EXTRACTION_IN_PROGRESS",
        "VALIDATION_FAILED",
        "RATE_LIMITED",
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
    analysis = await workflows.restart_extraction(
        db,
        document_id=document_id,
        user=current_user,
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
