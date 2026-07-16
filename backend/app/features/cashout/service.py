# backend/app/features/cashout/service.py

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.documents import DocumentRef
from app.errors import (
    BadRequestError,
    ForbiddenError,
    InvalidStateError,
    NotFoundError,
)
from app.features.users.model import User
from app.features.users.types import UserRole
from app.integrations.ai import AIAnalysisError
from app.integrations.storage import DocumentStorageClient

from .extraction import CashoutDocumentProcessor
from .models import (
    CashoutData,
    CashoutDocument,
    CashoutDocumentAnalysis,
    CashoutSubmission,
)
from .schemas import CashoutDataReview
from .types import (
    CashoutSubmissionStatus,
    DocumentAnalysisErrorCode,
    DocumentAnalysisStatus,
    DocumentUpload,
)

MAX_DOCUMENT_SIZE = 20 * 1024 * 1024

# Statuses from which a submission's documents may still change.
_EDITABLE_STATUSES = {
    CashoutSubmissionStatus.PROCESSING,
    CashoutSubmissionStatus.FAILED,
}


# ================================
# --------- Submissions ----------
# ================================


async def create_submission(db: AsyncSession, *, user_id: int) -> CashoutSubmission:
    # Cashouts are not shift-locked; a user may open one at any time.
    submission = CashoutSubmission(
        submitted_by_user_id=user_id,
        submitted_at=datetime.now(UTC),
    )
    db.add(submission)
    await db.flush()

    return submission


async def get_submission(
    db: AsyncSession, *, submission_id: int, user: User
) -> CashoutSubmission:
    stmt = (
        select(CashoutSubmission)
        .options(
            selectinload(CashoutSubmission.documents),
            joinedload(CashoutSubmission.data),
        )
        .where(CashoutSubmission.id == submission_id)
    )

    submission = (await db.execute(stmt)).scalar_one_or_none()
    if submission is None:
        raise NotFoundError("Cashout submission not found.")

    if user.role != UserRole.ADMIN and submission.submitted_by_user_id != user.id:
        raise ForbiddenError("You do not have access to this cashout submission.")

    return submission


# reconcile extracted data; UNDER_REVIEW if every document succeeded, FAILED otherwise
async def process_submission(
    db: AsyncSession, *, submission_id: int, user_id: int
) -> CashoutSubmission:
    submission = await _get_owned_submission(
        db, submission_id=submission_id, user_id=user_id
    )
    if submission.status not in _EDITABLE_STATUSES:
        raise InvalidStateError("This cashout has already been processed.")

    stmt = (
        select(CashoutDocument)
        .options(joinedload(CashoutDocument.analysis_result))
        .where(CashoutDocument.cashout_submission_id == submission.id)
    )
    documents = (await db.execute(stmt)).scalars().all()
    if not documents:
        raise InvalidStateError("Upload at least one document before processing.")

    # Every document needs one successful analysis before reconciliation.
    analyses = [document.analysis_result for document in documents]
    if any(
        analysis is None or analysis.status is not DocumentAnalysisStatus.SUCCEEDED
        for analysis in analyses
    ):
        submission.status = CashoutSubmissionStatus.FAILED
        return submission

    stmt = select(CashoutData).where(CashoutData.submission_id == submission.id)
    data = (await db.execute(stmt)).scalar_one_or_none()
    if data is None:
        data = CashoutData(submission_id=submission.id)
        db.add(data)

    data.extracted_data_json = _reconcile(documents)
    submission.status = CashoutSubmissionStatus.UNDER_REVIEW

    return submission


# ensure data has been reviewed, then close the submission out
async def complete_submission(
    db: AsyncSession, *, submission_id: int
) -> CashoutSubmission:
    submission = await CashoutSubmission.get_active(db, submission_id)
    if submission.status is not CashoutSubmissionStatus.UNDER_REVIEW:
        raise InvalidStateError("Only cashouts under review can be completed.")

    stmt = select(CashoutData).where(CashoutData.submission_id == submission.id)
    data = (await db.execute(stmt)).scalar_one_or_none()
    if data is None or data.reviewed_data_json is None:
        raise InvalidStateError("The extracted data must be reviewed first.")

    submission.status = CashoutSubmissionStatus.COMPLETED

    return submission


# ================================
# ---------- Documents -----------
# ================================


async def upload_document(
    db: AsyncSession,
    *,
    payload: DocumentUpload,
    submission_id: int,
    user_id: int,
    storage: DocumentStorageClient,
) -> CashoutDocument:
    submission = await _get_owned_submission(
        db, submission_id=submission_id, user_id=user_id
    )
    if submission.status not in _EDITABLE_STATUSES:
        raise InvalidStateError("Documents cannot be added after processing.")

    if len(payload.data) > MAX_DOCUMENT_SIZE:
        raise BadRequestError("Document exceeds the 20 MB size limit.")

    document = CashoutDocument(
        content_type=payload.content_type,
        storage_key=f"cashout/{submission.id}/{uuid4().hex}",
        original_filename=payload.original_filename,
        checksum_sha256=hashlib.sha256(payload.data).hexdigest(),
        uploaded_by_user_id=user_id,
        uploaded_at=datetime.now(UTC),
        cashout_submission_id=submission.id,
    )

    await storage.write(document.storage_key, payload.data)
    db.add(document)
    await db.flush()

    return document


async def extract_document(
    db: AsyncSession,
    *,
    document_id: int,
    user_id: int,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    document = await CashoutDocument.get_active(db, document_id)
    submission = await _get_owned_submission(
        db, submission_id=document.cashout_submission_id, user_id=user_id
    )
    if submission.status not in _EDITABLE_STATUSES:
        raise InvalidStateError("Documents cannot be analyzed after processing.")

    analysis = await _reset_analysis(db, document=document, processor=processor)

    ref = DocumentRef(
        storage_key=document.storage_key, content_type=document.content_type
    )
    try:
        result = await processor.process(ref)
    except AIAnalysisError as exc:
        # Persist the failure as a reviewable, retryable analysis.
        analysis.status = DocumentAnalysisStatus.FAILED
        analysis.error_code = exc.code.value
        analysis.error_message = exc.message
        analysis.completed_at = datetime.now(UTC)
        return analysis

    analysis.classification = result.classification.value
    analysis.classification_confidence = result.classification.confidence
    analysis.completed_at = datetime.now(UTC)

    if result.data is None:
        analysis.status = DocumentAnalysisStatus.FAILED
        analysis.error_code = DocumentAnalysisErrorCode.UNCLASSIFIED.value
        analysis.error_message = "The document could not be classified."
    else:
        analysis.status = DocumentAnalysisStatus.SUCCEEDED
        analysis.schema_name = result.schema_name
        analysis.extracted_data_json = result.data.model_dump(mode="json")
        analysis.extraction_confidence = result.confidence
        analysis.issues = [issue.model_dump(mode="json") for issue in result.issues]
        document.document_type = result.classification.value

    return analysis


# ================================
# ------------- Data -------------
# ================================


async def review_data(
    db: AsyncSession, *, payload: CashoutDataReview, data_id: int, user_id: int
) -> CashoutData:
    data = await CashoutData.get_active(db, data_id)

    submission = await CashoutSubmission.get_active(db, data.submission_id)
    if submission.status is not CashoutSubmissionStatus.UNDER_REVIEW:
        raise InvalidStateError("This cashout is not under review.")

    data.reviewed_data_json = payload.reviewed_data
    data.reviewed_by_user_id = user_id
    data.reviewed_at = datetime.now(UTC)

    return data


# ================================
# ----------- Helpers ------------
# ================================


async def _get_owned_submission(
    db: AsyncSession, *, submission_id: int, user_id: int
) -> CashoutSubmission:
    submission = await CashoutSubmission.get_active(db, submission_id)
    if submission.submitted_by_user_id != user_id:
        raise ForbiddenError("You do not have access to this cashout submission.")
    return submission


async def _reset_analysis(
    db: AsyncSession,
    *,
    document: CashoutDocument,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    """Create the document's analysis row, or reset it in place for a retry."""
    stmt = select(CashoutDocumentAnalysis).where(
        CashoutDocumentAnalysis.cashout_document_id == document.id
    )
    analysis = (await db.execute(stmt)).scalar_one_or_none()

    if analysis is not None and analysis.status is DocumentAnalysisStatus.SUCCEEDED:
        raise InvalidStateError("This document has already been analyzed.")

    if analysis is None:
        analysis = CashoutDocumentAnalysis(
            provider=processor.provider,
            model=processor.model,
            cashout_document_id=document.id,
        )
        db.add(analysis)
        await db.flush()
        return analysis

    analysis.provider = processor.provider
    analysis.model = processor.model
    analysis.status = DocumentAnalysisStatus.PROCESSING
    analysis.classification = None
    analysis.classification_confidence = None
    analysis.schema_name = None
    analysis.extracted_data_json = None
    analysis.extraction_confidence = None
    analysis.issues = None
    analysis.error_code = None
    analysis.error_message = None
    analysis.completed_at = None
    return analysis


def _reconcile(documents: Sequence[CashoutDocument]) -> dict[str, Any]:
    # TODO(document-ai): Real reconciliation (cross-checking totals between
    # document types) once the extraction schemas define real fields. For now
    # extracted data is grouped by document type.
    extracted: dict[str, list[Any]] = {}
    for document in documents:
        analysis = document.analysis_result
        if analysis is not None:
            extracted.setdefault(document.document_type.value, []).append(
                analysis.extracted_data_json
            )
    return dict(extracted)
