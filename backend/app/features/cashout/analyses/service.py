# backend/app/features/cashout/analyses/service.py

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.document_ai import DocumentRef
from app.errors import AppError
from app.features.cashout.documents.model import CashoutDocument
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.features.cashout.schemas import CashoutAnalysisVerify
from app.features.cashout.shared.access import ensure_can_view
from app.features.cashout.submissions.model import CashoutSubmission
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from app.features.users.model import User
from app.infrastructure.outbox import service as outbox_service
from app.integrations.ai import AIAnalysisError

from . import repository
from .messages import analysis_error_message
from .model import CashoutDocumentAnalysis
from .types import DocumentAnalysisStatus

logger = logging.getLogger(__name__)


async def start_extraction(
    db: AsyncSession,
    *,
    document: CashoutDocument,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    """Reset the document's analysis to EXTRACTING and queue the extraction.

    The message is enqueued in the caller's transaction, so it dispatches only
    once that transaction commits; the AI extraction itself runs from the
    outbox (`run_extraction` via the extraction handler). Clients poll the
    returned analysis.
    """
    analysis = await _reset_analysis(db, document=document, processor=processor)
    await outbox_service.enqueue(
        db,
        type="cashout.run_extraction",
        payload={"document_id": str(document.id)},
    )
    return analysis


async def restart_extraction(
    db: AsyncSession,
    *,
    document_id: UUID,
    user: User,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    """Reset a document's analysis and queue a fresh extraction attempt.

    As with upload, the extraction message is enqueued in this transaction
    and dispatches once the request commits. Verified analyses cannot be
    re-run, and an extraction already in flight cannot be restarted.
    """
    document = await _get_document(db, document_id)
    submission = await _get_submission_for_actor(
        db, submission_id=document.cashout_submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Documents cannot be analyzed after completion."
        )

    return await start_extraction(db, document=document, processor=processor)


async def run_extraction(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    document_id: UUID,
    processor: CashoutDocumentProcessor,
) -> None:
    """Outbox job: run the AI extraction and persist the outcome.

    Runs from the extraction handler after the upload/extract request has
    committed its EXTRACTING analysis, so it owns its session and
    transaction — the one sanctioned exception to "services never commit".
    All failures are handled here (the analysis is marked FAILED), so the
    outbox message completes even when the extraction does not.
    """
    async with sessionmaker() as db:
        try:
            document = await repository.get_document(db, document_id=document_id)
            if document is None:
                # Deleted between the request committing and this job running;
                # the cascade removed its analysis too — nothing to update.
                return
            await _apply_extraction(db, document=document, processor=processor)
            await db.commit()
            return
        except Exception:
            await db.rollback()
            logger.exception("Extraction failed for document %s", document_id)

    # Unexpected failure above: record it so the analysis doesn't sit in
    # EXTRACTING forever (which would block retries).
    async with sessionmaker() as db:
        analysis = await repository.find_analysis_by_document(
            db, document_id=document_id
        )
        if (
            analysis is not None
            and analysis.status is DocumentAnalysisStatus.EXTRACTING
        ):
            # No AI error code for an unexpected crash: error_code stays null
            # and the message is the generic default.
            analysis.status = DocumentAnalysisStatus.FAILED
            analysis.error_message = analysis_error_message()
            analysis.completed_at = datetime.now(UTC)
            await db.commit()


async def get_analysis(
    db: AsyncSession, *, analysis_id: UUID, user: User
) -> CashoutDocumentAnalysis:
    """Poll target for extraction progress; employee or admin."""
    analysis = await _get_analysis(db, analysis_id)

    document = await _get_document(db, analysis.cashout_document_id)
    submission = await _get_submission(db, document.cashout_submission_id)
    ensure_can_view(submission, user)

    return analysis


async def verify_analysis(
    db: AsyncSession,
    *,
    payload: CashoutAnalysisVerify,
    analysis_id: UUID,
    user: User,
) -> CashoutDocumentAnalysis:
    """Confirmation of an extraction (employee or admin), optionally corrected."""
    analysis = await _get_analysis(db, analysis_id)

    document = await _get_document(db, analysis.cashout_document_id)
    submission = await _get_submission_for_actor(
        db, submission_id=document.cashout_submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError("SUBMISSION_COMPLETED")

    if analysis.status is DocumentAnalysisStatus.VERIFIED:
        raise AppError("ANALYSIS_VERIFIED")
    if analysis.status is DocumentAnalysisStatus.EXTRACTING:
        raise AppError("EXTRACTION_IN_PROGRESS", "The extraction is still in progress.")
    if analysis.status is DocumentAnalysisStatus.FAILED:
        raise AppError("EXTRACTION_FAILED")

    # The actor either confirms the extraction as-is or submits corrections.
    if payload.verified_data is not None:
        analysis.verified_data_json = payload.verified_data
    else:
        analysis.verified_data_json = analysis.extracted_data_json

    analysis.status = DocumentAnalysisStatus.VERIFIED
    # The actual actor: the admin when an admin verifies for the employee.
    analysis.verified_by_user_id = user.id
    analysis.verified_at = datetime.now(UTC)

    return analysis


async def unverify_analysis(
    db: AsyncSession,
    *,
    analysis_id: UUID,
    user: User,
) -> CashoutDocumentAnalysis:
    """Send a verified extraction back through verification (employee or admin).

    Editing a verified extraction means re-verifying it: the verification
    outcome (verified data, verifier, timestamp) is cleared and the analysis
    returns to NEEDS_VERIFICATION, while the extraction fields stay untouched
    so the verification form re-renders from them. Combined with unsubmit,
    this is how an admin corrects an already-completed cashout.
    """
    analysis = await _get_analysis(db, analysis_id)

    document = await _get_document(db, analysis.cashout_document_id)
    submission = await _get_submission_for_actor(
        db, submission_id=document.cashout_submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError("SUBMISSION_COMPLETED")

    if analysis.status is not DocumentAnalysisStatus.VERIFIED:
        raise AppError("ANALYSIS_NOT_VERIFIED")

    analysis.status = DocumentAnalysisStatus.NEEDS_VERIFICATION
    analysis.verified_data_json = None
    analysis.verified_by_user_id = None
    analysis.verified_at = None

    return analysis


async def _get_analysis(db: AsyncSession, analysis_id: UUID) -> CashoutDocumentAnalysis:
    analysis = await repository.get_analysis(db, analysis_id=analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND")
    return analysis


async def _get_document(db: AsyncSession, document_id: UUID) -> CashoutDocument:
    document = await repository.get_document(db, document_id=document_id)
    if document is None:
        raise AppError("DOCUMENT_NOT_FOUND")
    return document


async def _get_submission(db: AsyncSession, submission_id: UUID) -> CashoutSubmission:
    submission = await repository.get_live_submission(db, submission_id=submission_id)
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


async def _apply_extraction(
    db: AsyncSession,
    *,
    document: CashoutDocument,
    processor: CashoutDocumentProcessor,
) -> None:
    """Run classification + extraction and persist the outcome on the analysis.

    Success lands the analysis in NEEDS_VERIFICATION — an UNKNOWN
    classification is not a failure, it simply has no extracted data. A
    provider failure lands it in FAILED with error_code/error_message.
    """
    analysis = await repository.find_analysis_by_document(db, document_id=document.id)
    if analysis is None:
        # Unreachable in practice: the reset created the row before this ran.
        raise RuntimeError("analysis missing for document under extraction")

    ref = DocumentRef(
        storage_key=document.storage_key, content_type=document.content_type
    )

    try:
        result = await processor.process(ref)
    except AIAnalysisError as exc:
        # Persist the code + a safe mapped message; the raw provider text can
        # leak internal detail, so keep it in the logs only.
        logger.warning(
            "Extraction failed for document %s (%s): %s",
            document.id,
            exc.code.value,
            exc.message,
        )
        analysis.status = DocumentAnalysisStatus.FAILED
        analysis.error_code = exc.code.value
        analysis.error_message = analysis_error_message(exc.code.value)
        analysis.completed_at = datetime.now(UTC)
        return

    analysis.status = DocumentAnalysisStatus.NEEDS_VERIFICATION
    analysis.classification = result.classification
    analysis.classification_confidence = result.classification_confidence
    analysis.completed_at = datetime.now(UTC)

    # An UNKNOWN classification has no schema: the extraction fields stay null.
    if result.data is not None:
        analysis.schema_name = result.schema_name
        analysis.extracted_data_json = result.data.model_dump(mode="json")
        analysis.extraction_confidence = result.confidence
        analysis.issues = [issue.model_dump(mode="json") for issue in result.issues]


async def _reset_analysis(
    db: AsyncSession,
    *,
    document: CashoutDocument,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    """Create the document's analysis row, or reset it in place for a retry."""
    analysis = await repository.find_analysis_by_document(db, document_id=document.id)

    if analysis is not None:
        if analysis.status is DocumentAnalysisStatus.VERIFIED:
            raise AppError(
                "ANALYSIS_VERIFIED", "This document has already been verified."
            )
        if analysis.status is DocumentAnalysisStatus.EXTRACTING:
            raise AppError("EXTRACTION_IN_PROGRESS")

    if analysis is None:
        analysis = CashoutDocumentAnalysis(
            provider=processor.provider,
            model=processor.model,
            cashout_document_id=document.id,
        )
        await repository.add_analysis(db, analysis)
        return analysis

    analysis.provider = processor.provider
    analysis.model = processor.model
    analysis.status = DocumentAnalysisStatus.EXTRACTING
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


__all__ = [
    "start_extraction",
    "restart_extraction",
    "run_extraction",
    "get_analysis",
    "verify_analysis",
    "unverify_analysis",
]
