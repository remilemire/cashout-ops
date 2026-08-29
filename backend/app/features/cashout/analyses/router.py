# backend/app/features/cashout/analyses/router.py

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from app.errors import error_responses
from app.features.auth.dependencies import get_current_user
from app.features.users.model import User
from app.infrastructure.db.dependencies import DbSession

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
