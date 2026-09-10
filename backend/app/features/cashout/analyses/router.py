# backend/app/features/cashout/analyses/router.py

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response

from app.errors import error_responses
from app.features.auth.dependencies import get_current_user
from app.features.users.model import User
from app.infrastructure.db.dependencies import DbSession
from app.integrations.storage import DocumentStorageClient
from app.integrations.storage.dependencies import get_document_storage
from app.lib.documents import DocumentContentType

from . import service as analyses_service
from .schemas import CashoutAnalysisVerify, CashoutDocumentAnalysisOut

router = APIRouter()

# Path parameters are UUIDs; Pydantic validates them (a malformed id → 422).
AnalysisId = Annotated[UUID, Path(description="Cashout document analysis ID.")]


@router.get(
    "/analyses/{analysis_id}",
    response_model=CashoutDocumentAnalysisOut,
    responses=error_responses("ANALYSIS_NOT_FOUND", "VALIDATION_FAILED"),
)
async def get_analysis(
    analysis_id: AnalysisId,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutDocumentAnalysisOut:
    """Poll a document analysis for its extraction progress.

    `EXTRACTING` means the AI is still running; it resolves to
    `NEEDS_VERIFICATION` or `FAILED`. Accessible to the submission's employee
    or an admin.
    """
    analysis = await analyses_service.get_analysis(
        db, analysis_id=analysis_id, user=current_user
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


_CROPPED_CONTENT_OK: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The crop of the document this analysis read.",
        # A crop is always an image: an image's crop keeps its format, and a
        # PDF's crops are cut from its rendered pages and stored as PNG.
        "content": {
            member.value: {}
            for member in DocumentContentType
            if member is not DocumentContentType.PDF
        },
    }
}


@router.get(
    "/analyses/{analysis_id}/cropped",
    response_class=Response,
    responses=_CROPPED_CONTENT_OK
    | error_responses("ANALYSIS_NOT_FOUND", "DOCUMENT_NOT_FOUND", "VALIDATION_FAILED"),
)
async def get_cropped_document(
    analysis_id: AnalysisId,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> Response:
    """Serve the crop of the document this analysis read, inline.

    The crop is the printed area text detection found on the first
    extraction — what the AI read, and what to check the extraction
    against. An analysis that read the upload whole (`croppedContentType`
    null: no detectable text, cropping off, a manual entry, or not yet
    extracted) has none, and the document's own content endpoint has the
    original.
    Accessible to the submission's employee or an admin.
    """
    content, original_filename = await analyses_service.get_cropped_document(
        db, analysis_id=analysis_id, user=current_user, storage=storage
    )
    filename = original_filename.replace('"', "")
    return Response(
        content=content.data,
        media_type=content.content_type.value,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutDocumentAnalysisOut:
    """Confirm an extraction, optionally submitting corrected values.

    Marks the analysis `VERIFIED`. `verifiedData` overrides the extracted data;
    omit it to confirm the extraction as-is. The submission's employee or an
    admin may verify; the verifying user is recorded.
    """
    analysis = await analyses_service.verify_analysis(
        db, payload=payload, analysis_id=analysis_id, user=current_user
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


@router.post(
    "/analyses/{analysis_id}/unverify",
    response_model=CashoutDocumentAnalysisOut,
    responses=error_responses(
        "ANALYSIS_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "ANALYSIS_NOT_VERIFIED",
        "VALIDATION_FAILED",
    ),
)
async def unverify_analysis(
    analysis_id: AnalysisId,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutDocumentAnalysisOut:
    """Send a verified extraction back through verification for editing.

    Clears the verification (verified data, verifier, timestamp) and returns
    the analysis to `NEEDS_VERIFICATION`; the extraction fields are kept, so
    the verification form re-renders from them. The submission's employee or
    an admin may unverify, and only while the submission is `PROCESSING` —
    combined with unsubmit, this is how an admin corrects an
    already-completed cashout.
    """
    analysis = await analyses_service.unverify_analysis(
        db, analysis_id=analysis_id, user=current_user
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


__all__ = ["router"]
