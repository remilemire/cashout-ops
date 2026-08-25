# backend/app/features/cashout/service.py

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.document_ai import DocumentRef
from app.errors import AppError
from app.features.cashout.analyses.types import DocumentAnalysisStatus
from app.features.cashout.documents.types import DocumentUpload
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from app.features.users.model import User
from app.features.users.types import UserRole
from app.infrastructure.outbox import service as outbox_service
from app.integrations.ai import AIAnalysisError
from app.integrations.storage import DocumentStorageClient

from . import repository
from .analysis_errors import analysis_error_message
from .extraction import CashoutDocumentProcessor
from .models import (
    CashoutData,
    CashoutDocument,
    CashoutDocumentAnalysis,
    CashoutSubmission,
)
from .schemas import CashoutAnalysisVerify

logger = logging.getLogger(__name__)

# The flow, per document: the cashier uploads it and immediately gets back an
# EXTRACTING analysis; the AI extraction runs in a background task and the
# client polls the analysis until it reaches NEEDS_VERIFICATION (or FAILED,
# retryable via the extract endpoint). The cashier verifies each analysis —
# optionally submitting corrections. Once every document is verified,
# completing the submission reconciles the analyses into a CashoutData row and
# closes the cashout (COMPLETED).


# ================================
# --------- Submissions ----------
# ================================


async def create_submission(db: AsyncSession, *, user_id: UUID) -> CashoutSubmission:
    # Cashouts are not shift-locked; a user may open one at any time. The
    # creator is the cashout's employee.
    submission = CashoutSubmission(
        employee_user_id=user_id,
        submitted_at=datetime.now(UTC),
    )
    await repository.add_submission(db, submission)

    return submission


async def delete_submission(
    db: AsyncSession,
    *,
    submission_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> None:
    """Delete a submission (employee or admin); a completed one never can be.

    A PROCESSING submission with no traces at all — no documents, no
    reconciled data, never completed — is removed outright. Anything else is
    soft-deleted (deleted_at stamped): the row, its documents, analyses, and
    stored files survive, but every lookup excludes it.
    """
    submission = await _get_submission_for_actor(
        db, submission_id=submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError("SUBMISSION_COMPLETED", "A completed cashout cannot be deleted.")

    # The reconciled data is fully derived from the submission, so it goes
    # with it — either path. In practice unsubmit already removed it (that is
    # the only way a PROCESSING submission relates to a data row); the
    # RESTRICT FK stays as the safety net should a future path forget.
    data = await repository.find_data_by_submission(db, submission_id=submission.id)
    if data is not None:
        await repository.delete_data(db, data)

    storage_keys = await repository.list_storage_keys(db, submission_id=submission.id)
    has_traces = (
        bool(storage_keys)  # one key per document
        or data is not None
        or submission.first_completed_at is not None
    )
    if has_traces:
        submission.deleted_at = datetime.now(UTC)
        return

    await repository.delete_submission(db, submission)

    # Vacuously empty here (no traces means no documents), kept so a future
    # hard-delete path cannot leak stored files.
    for storage_key in storage_keys:
        await storage.delete(storage_key)


async def get_submission(
    db: AsyncSession, *, submission_id: UUID, user: User
) -> CashoutSubmission:
    submission = await repository.get_submission_with_details(
        db, submission_id=submission_id
    )
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND")

    _ensure_can_view(submission, user)

    return submission


async def list_submissions(
    db: AsyncSession, *, user: User
) -> Sequence[CashoutSubmission]:
    """Admins (and the owner) see every submission; cashiers only their own.
    Newest first."""
    is_admin = user.role in (UserRole.ADMIN, UserRole.OWNER)
    only_user_id = None if is_admin else user.id
    return await repository.list_submissions(db, only_user_id=only_user_id)


async def complete_submission(
    db: AsyncSession, *, submission_id: UUID, user: User
) -> CashoutSubmission:
    """Reconcile the verified analyses into a CashoutData and close the cashout."""
    submission = await _get_submission_for_actor(
        db, submission_id=submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError("SUBMISSION_COMPLETED")

    documents = await repository.list_documents_with_analysis(
        db, submission_id=submission.id
    )
    if not documents:
        raise AppError("SUBMISSION_EMPTY")

    analyses: list[CashoutDocumentAnalysis] = []
    for document in documents:
        analysis = document.analysis
        if analysis is None or analysis.status is not DocumentAnalysisStatus.VERIFIED:
            raise AppError("SUBMISSION_UNVERIFIED")
        analyses.append(analysis)

    await repository.add_data(db, _reconcile(submission.id, analyses))
    submission.status = CashoutSubmissionStatus.COMPLETED
    # Record the actual actor (the admin when an admin completes); the first
    # completion time is bookkeeping — set once, never overwritten.
    submission.completed_by_user_id = user.id
    if submission.first_completed_at is None:
        submission.first_completed_at = datetime.now(UTC)

    return submission


async def unsubmit_submission(
    db: AsyncSession, *, submission_id: UUID
) -> CashoutSubmission:
    """Reopen a completed cashout: drop its reconciled data, back to PROCESSING.

    Admin-only (enforced at the route). The analyses stay VERIFIED, so
    completing again reconciles them into a fresh data row.
    """
    submission = await _get_submission(db, submission_id)
    if submission.status is not CashoutSubmissionStatus.COMPLETED:
        raise AppError("SUBMISSION_NOT_COMPLETED")

    data = await repository.find_data_by_submission(db, submission_id=submission.id)
    if data is not None:
        await repository.delete_data(db, data)

    submission.status = CashoutSubmissionStatus.PROCESSING
    # completed_by reflects the *current* completion, so it clears with it;
    # first_completed_at is permanent bookkeeping and survives.
    submission.completed_by_user_id = None

    return submission


# ================================
# ---------- Documents -----------
# ================================


async def upload_document(
    db: AsyncSession,
    *,
    payload: DocumentUpload,
    submission_id: UUID,
    user: User,
    storage: DocumentStorageClient,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    """Store the document, create its EXTRACTING analysis, and queue extraction.

    The AI extraction itself runs from the outbox (`run_extraction` via the
    extraction handler); the message is enqueued in this transaction, so it
    dispatches only once the upload commits. Clients poll the returned
    analysis.
    """
    submission = await _get_submission_for_actor(
        db, submission_id=submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Documents cannot be added after completion."
        )

    # The router already stops reading past the limit, so this normally sees
    # the single byte of overshoot; it stays as the authoritative check for
    # callers that assembled the payload some other way.
    if len(payload.data) > settings.storage.MAX_DOCUMENT_SIZE_BYTES:
        raise AppError("DOCUMENT_TOO_LARGE")

    document = CashoutDocument(
        content_type=payload.content_type,
        storage_key=f"cashout/{submission.id}/{uuid4().hex}",
        original_filename=payload.original_filename,
        checksum_sha256=hashlib.sha256(payload.data).hexdigest(),
        # The actual actor: the admin when an admin uploads for the employee.
        uploaded_by_user_id=user.id,
        uploaded_at=datetime.now(UTC),
        cashout_submission_id=submission.id,
    )

    await repository.add_document(db, document)
    await storage.write(document.storage_key, payload.data)

    analysis = await _reset_analysis(db, document=document, processor=processor)
    await outbox_service.enqueue(
        db,
        type="cashout.run_extraction",
        payload={"document_id": str(document.id)},
    )
    return analysis


async def delete_document(
    db: AsyncSession,
    *,
    document_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> None:
    """Remove a document (and its analysis) from an incomplete submission."""
    document = await _get_document(db, document_id)
    submission = await _get_submission_for_actor(
        db, submission_id=document.cashout_submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Documents cannot be removed after completion."
        )

    await repository.delete_document(db, document)
    await storage.delete(document.storage_key)


async def get_document_content(
    db: AsyncSession,
    *,
    document_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> tuple[CashoutDocument, bytes]:
    """The original uploaded bytes, for viewing; employee or admin."""
    document = await _get_document(db, document_id)
    submission = await _get_submission(db, document.cashout_submission_id)
    _ensure_can_view(submission, user)

    return document, await storage.read(document.storage_key)


async def extract_document(
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

    analysis = await _reset_analysis(db, document=document, processor=processor)
    await outbox_service.enqueue(
        db,
        type="cashout.run_extraction",
        payload={"document_id": str(document_id)},
    )
    return analysis


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


# ================================
# ---------- Analyses ------------
# ================================


async def get_analysis(
    db: AsyncSession, *, analysis_id: UUID, user: User
) -> CashoutDocumentAnalysis:
    """Poll target for extraction progress; employee or admin."""
    analysis = await _get_analysis(db, analysis_id)

    document = await _get_document(db, analysis.cashout_document_id)
    submission = await _get_submission(db, document.cashout_submission_id)
    _ensure_can_view(submission, user)

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


# ================================
# ------------- Data -------------
# ================================


async def list_data(db: AsyncSession) -> Sequence[CashoutData]:
    """Every reconciled cashout data row, newest first (admin table)."""
    return await repository.list_data(db)


# ================================
# ----------- Helpers ------------
# ================================


async def _get_submission(db: AsyncSession, submission_id: UUID) -> CashoutSubmission:
    submission = await repository.get_submission(db, submission_id=submission_id)
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND")
    return submission


async def _get_document(db: AsyncSession, document_id: UUID) -> CashoutDocument:
    document = await repository.get_document(db, document_id=document_id)
    if document is None:
        raise AppError("DOCUMENT_NOT_FOUND")
    return document


async def _get_analysis(db: AsyncSession, analysis_id: UUID) -> CashoutDocumentAnalysis:
    analysis = await repository.get_analysis(db, analysis_id=analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND")
    return analysis


async def _get_submission_for_actor(
    db: AsyncSession, *, submission_id: UUID, actor: User
) -> CashoutSubmission:
    """Fetch a submission the actor may act on: its employee, or any admin.

    Admins (and the owner) have full control over every cashout, so acting
    and viewing share the same rule.
    """
    submission = await _get_submission(db, submission_id)
    _ensure_can_view(submission, actor)
    return submission


def _ensure_can_view(submission: CashoutSubmission, user: User) -> None:
    is_admin = user.role in (UserRole.ADMIN, UserRole.OWNER)
    if not is_admin and submission.employee_user_id != user.id:
        raise AppError(
            "FORBIDDEN", "You do not have access to this cashout submission."
        )


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


def _reconcile(
    submission_id: UUID, analyses: Sequence[CashoutDocumentAnalysis]
) -> CashoutData:
    # TODO(document-ai): real reconciliation (cross-checking totals between the
    # verified analyses) once the extraction schemas define real fields. Until
    # then the placeholder columns stay NULL.
    _ = analyses
    return CashoutData(submission_id=submission_id)
