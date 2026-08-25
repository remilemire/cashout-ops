# backend/app/features/cashout/analyses/router.py

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import error_responses
from app.features.auth.dependencies import get_current_user
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.features.cashout.extraction.dependencies import (
    get_cashout_document_processor,
)
from app.features.users.model import User
from app.infrastructure.db.dependencies import get_db

from . import service as analyses_service
from .dependencies import rate_limit_extract
from .schemas import CashoutAnalysisVerify, CashoutDocumentAnalysisOut

router = APIRouter()

# Path parameters are UUIDs; Pydantic validates them (a malformed id → 422).
DocumentId = Annotated[UUID, Path(description="Cashout document ID.")]
AnalysisId = Annotated[UUID, Path(description="Cashout document analysis ID.")]


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
    analysis = await analyses_service.restart_extraction(
        db,
        document_id=document_id,
        user=current_user,
        processor=processor,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


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
    `NEEDS_VERIFICATION` or `FAILED`. Accessible to the submission's employee
    or an admin.
    """
    analysis = await analyses_service.get_analysis(
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
    db: Annotated[AsyncSession, Depends(get_db)],
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
