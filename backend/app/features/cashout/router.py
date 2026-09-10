# backend/app/features/cashout/router.py

"""The flow, per upload (the file the cashier submits): the cashier uploads it
and immediately gets back an EXTRACTING analysis; the AI extraction runs in a
background task, first finding every document printed in the upload (two
receipts in one photo, the pages of a PDF) and giving each document its own
analysis, and the client polls each analysis until it reaches
NEEDS_VERIFICATION (or FAILED — a provider failure, or a document the AI
could not place as a cashout report — retryable via the analysis's extract
endpoint; the upload's extract endpoint starts the upload over, detecting its
documents again). The cashier verifies each analysis — optionally submitting
corrections. Alternatively, an upload can be added with manually entered
details (or a failed/unverified analysis replaced by them), skipping AI
entirely and landing directly in VERIFIED. Once every analysis is verified,
completing the submission reconciles them into a CashoutData row and closes
the cashout (COMPLETED) — or refuses, when the documents do not cross-check
(see data/reconciliation.py).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Path, UploadFile, status

from app.core.config import settings
from app.errors import AppError, error_responses
from app.features.auth.dependencies import get_current_user
from app.features.users.model import User
from app.infrastructure.db.dependencies import DbSession
from app.integrations.storage import DocumentStorageClient
from app.integrations.storage.dependencies import get_document_storage
from app.lib.documents import DocumentContentType, read_document
from app.security.dependencies import require_csrf

from .analyses.router import router as analyses_router
from .analyses.schemas import (
    CashoutAnalysisExtract,
    CashoutDocumentAnalysisOut,
    CashoutDocumentManualEntry,
)
from .data.router import router as data_router
from .dependencies import rate_limit_extract, rate_limit_upload
from .extraction import CashoutDocumentProcessor
from .extraction.dependencies import get_cashout_document_processor
from .shared import workflows
from .submissions.router import router as submissions_router
from .uploads.router import router as uploads_router
from .uploads.types import UploadPayload

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
# Upload removal and inline viewing.
router.include_router(uploads_router)
# Analysis polling and verification.
router.include_router(analyses_router)
# The reconciled cashout data (admin table).
router.include_router(data_router)

# The upload workflows' HTTP entry points: these routes cross sub-feature URL
# spaces and coordinate across sub-features, so they live at the namespace
# root and call shared/workflows — mirroring auth's root logout → shared/access.

# Path parameters are UUIDs; Pydantic validates them (a malformed id → 422).
SubmissionId = Annotated[UUID, Path(description="Cashout submission ID.")]
UploadId = Annotated[UUID, Path(description="Cashout upload ID.")]
AnalysisId = Annotated[UUID, Path(description="Cashout document analysis ID.")]


@router.post(
    "/submissions/{submission_id}/uploads",
    response_model=CashoutDocumentAnalysisOut,
    status_code=status.HTTP_201_CREATED,
    # Each upload here starts an AI extraction, so it draws on the per-user
    # quota; the manual route below shares the same intake quota.
    dependencies=[Depends(rate_limit_upload)],
    responses=error_responses(
        "UNSUPPORTED_UPLOAD_TYPE",
        "UPLOAD_TOO_LARGE",
        "UPLOAD_DUPLICATE",
        "SUBMISSION_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "VALIDATION_FAILED",
        "RATE_LIMITED",
    ),
)
async def create_upload(
    submission_id: SubmissionId,
    file: UploadFile,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
    processor: Annotated[
        CashoutDocumentProcessor, Depends(get_cashout_document_processor)
    ],
) -> CashoutDocumentAnalysisOut:
    """Upload an end-of-shift file and start extracting the documents in it.

    Accepts JPEG, PNG, WebP, or PDF within the configured size limit
    (`STORAGE_MAX_DOCUMENT_SIZE_MB`); a file already uploaded to this
    submission (same checksum) is rejected. The AI extraction runs in the
    background: this returns the upload's first analysis in `EXTRACTING`;
    poll `GET /cashout/analyses/{id}` until it reaches `NEEDS_VERIFICATION`
    or `FAILED` (retry via the analysis's extract endpoint). The extraction
    first finds every document printed in the upload (several receipts in
    one photo, each page of a PDF) and gives each further one its own
    analysis, listed on the upload in the submission detail.

    The content type is checked before the body is read, and the body itself is
    read only up to the limit (plus the byte that proves it was exceeded); the
    service rejects it from there.
    """
    # Resolved first so an unsupported type is rejected without reading the
    # file: keyword arguments evaluate in order, so this cannot be inlined
    # below `data` without reading the body of a file we are about to refuse.
    content_type = _to_content_type(file.content_type)
    payload = UploadPayload(
        data=await read_document(file, limit=settings.storage.MAX_DOCUMENT_SIZE_BYTES),
        content_type=content_type,
        original_filename=file.filename or "upload",
    )
    analysis = await workflows.create_upload(
        db,
        payload=payload,
        submission_id=submission_id,
        user=current_user,
        storage=storage,
        processor=processor,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


@router.post(
    "/submissions/{submission_id}/uploads/manual",
    response_model=CashoutDocumentAnalysisOut,
    status_code=status.HTTP_201_CREATED,
    # No AI runs here, but the file still lands in storage — manual additions
    # draw on the same per-user intake quota as extracting uploads.
    dependencies=[Depends(rate_limit_upload)],
    responses=error_responses(
        "UNSUPPORTED_UPLOAD_TYPE",
        "UPLOAD_TOO_LARGE",
        "UPLOAD_DUPLICATE",
        "SUBMISSION_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "VALIDATION_FAILED",
        "RATE_LIMITED",
    ),
)
async def create_manual_upload(
    submission_id: SubmissionId,
    file: UploadFile,
    payload: Annotated[str, Form(description="JSON object: `{classification, data}`.")],
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> CashoutDocumentAnalysisOut:
    """Upload a file with its document's manually entered details, skipping
    AI entirely.

    The multipart `payload` field carries `{classification, data}`: the data
    is validated against the classification's registered schema. Typing the
    values is the verification, so the analysis lands directly in `VERIFIED`
    — there is nothing to poll. No extraction ever runs for it, so the upload
    is never split: it stands for one document.

    As on the extracting upload, the content type is checked before the body
    is read, and the body itself is read only up to the limit (plus the byte
    that proves it was exceeded).
    """
    # Parsed first, like the content-type check below: a malformed entry is
    # rejected without reading the body of a file we are about to refuse.
    entry = CashoutDocumentManualEntry.model_validate_json(payload)
    content_type = _to_content_type(file.content_type)
    upload = UploadPayload(
        data=await read_document(file, limit=settings.storage.MAX_DOCUMENT_SIZE_BYTES),
        content_type=content_type,
        original_filename=file.filename or "upload",
    )
    analysis = await workflows.create_manual_upload(
        db,
        payload=upload,
        submission_id=submission_id,
        classification=entry.classification,
        data=entry.data,
        user=current_user,
        storage=storage,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


@router.post(
    "/analyses/{analysis_id}/manual",
    response_model=CashoutDocumentAnalysisOut,
    # No rate limit: like verify, a manual entry costs no AI or storage.
    responses=error_responses(
        "ANALYSIS_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "ANALYSIS_VERIFIED",
        "EXTRACTION_IN_PROGRESS",
        "VALIDATION_FAILED",
    ),
)
async def replace_with_manual_entry(
    analysis_id: AnalysisId,
    payload: CashoutDocumentManualEntry,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutDocumentAnalysisOut:
    """Replace an analysis with manually entered details.

    Skips AI entirely: the entered data is validated against the
    classification's registered schema and the analysis lands directly in
    `VERIFIED` — typing the values is the verification. Allowed from `FAILED`
    and `NEEDS_VERIFICATION`; a verified analysis cannot be replaced, nor one
    whose extraction is still in progress. The crop the analysis read stays
    its preview.
    """
    analysis = await workflows.replace_with_manual_entry(
        db,
        analysis_id=analysis_id,
        classification=payload.classification,
        data=payload.data,
        user=current_user,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


@router.post(
    "/analyses/{analysis_id}/extract",
    response_model=CashoutDocumentAnalysisOut,
    # Re-extraction burns provider tokens on demand — per-user quota applies.
    dependencies=[Depends(rate_limit_extract)],
    responses=error_responses(
        "ANALYSIS_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "ANALYSIS_VERIFIED",
        "EXTRACTION_IN_PROGRESS",
        "VALIDATION_FAILED",
        "RATE_LIMITED",
    ),
)
async def extract_analysis(
    analysis_id: AnalysisId,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    processor: Annotated[
        CashoutDocumentProcessor, Depends(get_cashout_document_processor)
    ],
    # The body is optional: a bare POST is the plain retry.
    payload: CashoutAnalysisExtract | None = None,
) -> CashoutDocumentAnalysisOut:
    """Re-run one analysis (e.g. after a `FAILED` attempt).

    Resets the analysis to `EXTRACTING` and runs the AI in the background
    over the crop it read before — poll `GET /cashout/analyses/{id}` for the
    outcome. A verified analysis cannot be re-run, nor one whose extraction
    is still in progress. To detect the documents in the upload again, use
    the upload's extract endpoint instead.

    With a `classification` in the body (the user correcting a
    misclassification), the rerun skips AI classification and extracts
    straight into that type's schema; the recorded classification confidence
    is then null. Without one, the full classify + extract pipeline runs.
    """
    analysis = await workflows.retry_extraction(
        db,
        analysis_id=analysis_id,
        user=current_user,
        processor=processor,
        classification=payload.classification if payload is not None else None,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


@router.post(
    "/uploads/{upload_id}/extract",
    response_model=CashoutDocumentAnalysisOut,
    # Starting over burns provider tokens on demand — per-user quota applies.
    dependencies=[Depends(rate_limit_extract)],
    responses=error_responses(
        "UPLOAD_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "ANALYSIS_VERIFIED",
        "EXTRACTION_IN_PROGRESS",
        "VALIDATION_FAILED",
        "RATE_LIMITED",
    ),
)
async def extract_upload(
    upload_id: UploadId,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
    processor: Annotated[
        CashoutDocumentProcessor, Depends(get_cashout_document_processor)
    ],
) -> CashoutDocumentAnalysisOut:
    """Start an upload over: detect the documents in it again and re-extract
    them all.

    Every current analysis of the upload, and the crop each read, is
    discarded; a fresh `EXTRACTING` analysis is returned, and the background
    job adds one for each further document it finds — refresh the submission
    for them. Refused while any analysis is verified or still extracting.
    The way to recover from a wrong split or crop; to re-run just one
    analysis, use its own extract endpoint.
    """
    analysis = await workflows.restart_extraction(
        db,
        upload_id=upload_id,
        user=current_user,
        processor=processor,
        storage=storage,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


def _to_content_type(content_type: str | None) -> DocumentContentType:
    try:
        return DocumentContentType(content_type or "")
    except ValueError:
        raise AppError(
            "UNSUPPORTED_UPLOAD_TYPE",
            f"Unsupported upload content type: {content_type!r}.",
        ) from None


__all__ = ["router"]
