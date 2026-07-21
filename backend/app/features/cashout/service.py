# backend/app/features/cashout/service.py

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import partial
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload, selectinload

from app.dependencies.background import PostCommitTasks
from app.documents import DocumentRef
from app.errors import AppError
from app.features.users.model import User
from app.integrations.ai import AIAnalysisError
from app.integrations.storage import DocumentStorageClient

from .analysis_errors import analysis_error_message
from .extraction import CashoutDocumentProcessor
from .models import (
    CashoutData,
    CashoutDocument,
    CashoutDocumentAnalysis,
    CashoutSubmission,
)
from .schemas import CashoutAnalysisVerify
from .types import (
    CashoutSubmissionStatus,
    DocumentAnalysisStatus,
    DocumentUpload,
)

logger = logging.getLogger(__name__)

MAX_DOCUMENT_SIZE = 20 * 1024 * 1024

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
    # Cashouts are not shift-locked; a user may open one at any time.
    submission = CashoutSubmission(
        submitted_by_user_id=user_id,
        submitted_at=datetime.now(UTC),
    )
    db.add(submission)
    await db.flush()

    return submission


async def delete_submission(
    db: AsyncSession,
    *,
    submission_id: UUID,
    user_id: UUID,
    storage: DocumentStorageClient,
) -> None:
    """Delete an owned submission unless reconciled data references it."""
    submission = await _get_owned_submission(
        db, submission_id=submission_id, user_id=user_id
    )
    storage_keys = list(
        await db.scalars(
            select(CashoutDocument.storage_key).where(
                CashoutDocument.cashout_submission_id == submission.id
            )
        )
    )

    await db.delete(submission)
    # Surface the cashout_data ON DELETE RESTRICT violation before removing
    # document objects or returning a successful response.
    await db.flush()

    for storage_key in storage_keys:
        await storage.delete(storage_key)


async def get_submission(
    db: AsyncSession, *, submission_id: UUID, user: User
) -> CashoutSubmission:
    stmt = (
        select(CashoutSubmission)
        .options(
            selectinload(CashoutSubmission.documents).joinedload(
                CashoutDocument.analysis
            ),
            joinedload(CashoutSubmission.data),
            joinedload(CashoutSubmission.submitted_by),
        )
        .where(CashoutSubmission.id == submission_id)
    )

    submission = (await db.execute(stmt)).scalar_one_or_none()
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND")

    _ensure_can_view(submission, user)

    return submission


async def list_submissions(
    db: AsyncSession, *, user: User
) -> Sequence[CashoutSubmission]:
    """Admins see every submission; cashiers only their own. Newest first."""
    stmt = (
        select(CashoutSubmission)
        .options(joinedload(CashoutSubmission.submitted_by))
        .order_by(CashoutSubmission.submitted_at.desc())
    )
    if not user.is_admin:
        stmt = stmt.where(CashoutSubmission.submitted_by_user_id == user.id)

    return (await db.execute(stmt)).scalars().all()


async def complete_submission(
    db: AsyncSession, *, submission_id: UUID, user_id: UUID
) -> CashoutSubmission:
    """Reconcile the verified analyses into a CashoutData and close the cashout."""
    submission = await _get_owned_submission(
        db, submission_id=submission_id, user_id=user_id
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError("SUBMISSION_COMPLETED")

    stmt = (
        select(CashoutDocument)
        .options(joinedload(CashoutDocument.analysis))
        .where(CashoutDocument.cashout_submission_id == submission.id)
    )
    documents = (await db.execute(stmt)).scalars().all()
    if not documents:
        raise AppError("SUBMISSION_EMPTY")

    analyses: list[CashoutDocumentAnalysis] = []
    for document in documents:
        analysis = document.analysis
        if analysis is None or analysis.status is not DocumentAnalysisStatus.VERIFIED:
            raise AppError("SUBMISSION_UNVERIFIED")
        analyses.append(analysis)

    db.add(_reconcile(submission.id, analyses))
    submission.status = CashoutSubmissionStatus.COMPLETED

    return submission


# ================================
# ---------- Documents -----------
# ================================


async def upload_document(
    db: AsyncSession,
    *,
    payload: DocumentUpload,
    submission_id: UUID,
    user_id: UUID,
    storage: DocumentStorageClient,
    processor: CashoutDocumentProcessor,
    post_commit: PostCommitTasks,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> CashoutDocumentAnalysis:
    """Store the document, create its EXTRACTING analysis, and queue extraction.

    The AI extraction itself runs in a post-commit background job
    (`run_extraction`), queued here to run once the request transaction
    commits; clients poll the returned analysis.
    """
    submission = await _get_owned_submission(
        db, submission_id=submission_id, user_id=user_id
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Documents cannot be added after completion."
        )

    if len(payload.data) > MAX_DOCUMENT_SIZE:
        raise AppError("DOCUMENT_TOO_LARGE")

    document = CashoutDocument(
        content_type=payload.content_type,
        storage_key=f"cashout/{submission.id}/{uuid4().hex}",
        original_filename=payload.original_filename,
        checksum_sha256=hashlib.sha256(payload.data).hexdigest(),
        uploaded_by_user_id=user_id,
        uploaded_at=datetime.now(UTC),
        cashout_submission_id=submission.id,
    )

    # Flush before writing to storage: the (submission, checksum) unique index
    # rejects a duplicate upload before its bytes land in the object store.
    db.add(document)
    await db.flush()
    await storage.write(document.storage_key, payload.data)

    analysis = await _reset_analysis(db, document=document, processor=processor)
    post_commit.add(
        partial(
            run_extraction,
            sessionmaker,
            document_id=document.id,
            processor=processor,
        )
    )
    return analysis


async def delete_document(
    db: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
    storage: DocumentStorageClient,
) -> None:
    """Remove a document (and its analysis) from an incomplete submission."""
    document = await _get_document(db, document_id)
    submission = await _get_owned_submission(
        db, submission_id=document.cashout_submission_id, user_id=user_id
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Documents cannot be removed after completion."
        )

    await db.delete(document)
    # Flush so a database failure surfaces before the stored bytes are gone.
    await db.flush()
    await storage.delete(document.storage_key)


async def get_document_content(
    db: AsyncSession,
    *,
    document_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> tuple[CashoutDocument, bytes]:
    """The original uploaded bytes, for viewing; owner or admin."""
    document = await _get_document(db, document_id)
    submission = await _get_submission(db, document.cashout_submission_id)
    _ensure_can_view(submission, user)

    return document, await storage.read(document.storage_key)


async def extract_document(
    db: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
    processor: CashoutDocumentProcessor,
    post_commit: PostCommitTasks,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> CashoutDocumentAnalysis:
    """Reset a document's analysis and queue a fresh extraction attempt.

    As with upload, the extraction itself runs in a post-commit background
    job, queued here to run once the request transaction commits. Verified
    analyses cannot be re-run, and an extraction already in flight cannot be
    restarted.
    """
    document = await _get_document(db, document_id)
    submission = await _get_owned_submission(
        db, submission_id=document.cashout_submission_id, user_id=user_id
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Documents cannot be analyzed after completion."
        )

    analysis = await _reset_analysis(db, document=document, processor=processor)
    post_commit.add(
        partial(
            run_extraction,
            sessionmaker,
            document_id=document_id,
            processor=processor,
        )
    )
    return analysis


async def run_extraction(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    document_id: UUID,
    processor: CashoutDocumentProcessor,
) -> None:
    """Background task: run the AI extraction and persist the outcome.

    Runs after the upload/extract request has committed its EXTRACTING
    analysis, so it owns its session and transaction — the one sanctioned
    exception to "services never commit".
    """
    async with sessionmaker() as db:
        try:
            document = await CashoutDocument.find_by_id(db, document_id)
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
        stmt = select(CashoutDocumentAnalysis).where(
            CashoutDocumentAnalysis.cashout_document_id == document_id
        )
        analysis = (await db.execute(stmt)).scalar_one_or_none()
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
    """Poll target for extraction progress; owner or admin."""
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
    user_id: UUID,
) -> CashoutDocumentAnalysis:
    """Cashier confirmation of an extraction, optionally with corrections."""
    analysis = await _get_analysis(db, analysis_id)

    document = await _get_document(db, analysis.cashout_document_id)
    submission = await _get_owned_submission(
        db, submission_id=document.cashout_submission_id, user_id=user_id
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError("SUBMISSION_COMPLETED")

    if analysis.status is DocumentAnalysisStatus.VERIFIED:
        raise AppError("ANALYSIS_VERIFIED")
    if analysis.status is DocumentAnalysisStatus.EXTRACTING:
        raise AppError("EXTRACTION_IN_PROGRESS", "The extraction is still in progress.")
    if analysis.status is DocumentAnalysisStatus.FAILED:
        raise AppError("EXTRACTION_FAILED")

    # The cashier either confirms the extraction as-is or submits corrections.
    if payload.verified_data is not None:
        analysis.verified_data_json = payload.verified_data
    else:
        analysis.verified_data_json = analysis.extracted_data_json

    analysis.status = DocumentAnalysisStatus.VERIFIED
    analysis.verified_by_user_id = user_id
    analysis.verified_at = datetime.now(UTC)

    return analysis


# ================================
# ------------- Data -------------
# ================================


async def list_data(db: AsyncSession) -> Sequence[CashoutData]:
    """Every reconciled cashout data row, newest first (admin table)."""
    stmt = select(CashoutData).order_by(CashoutData.created_at.desc())
    return (await db.execute(stmt)).scalars().all()


# ================================
# ----------- Helpers ------------
# ================================


async def _get_submission(db: AsyncSession, submission_id: UUID) -> CashoutSubmission:
    submission = await CashoutSubmission.find_by_id(db, submission_id)
    if submission is None:
        raise AppError("SUBMISSION_NOT_FOUND")
    return submission


async def _get_document(db: AsyncSession, document_id: UUID) -> CashoutDocument:
    document = await CashoutDocument.find_by_id(db, document_id)
    if document is None:
        raise AppError("DOCUMENT_NOT_FOUND")
    return document


async def _get_analysis(db: AsyncSession, analysis_id: UUID) -> CashoutDocumentAnalysis:
    analysis = await CashoutDocumentAnalysis.find_by_id(db, analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND")
    return analysis


async def _get_owned_submission(
    db: AsyncSession, *, submission_id: UUID, user_id: UUID
) -> CashoutSubmission:
    submission = await _get_submission(db, submission_id)
    if submission.submitted_by_user_id != user_id:
        raise AppError(
            "FORBIDDEN", "You do not have access to this cashout submission."
        )
    return submission


def _ensure_can_view(submission: CashoutSubmission, user: User) -> None:
    if not user.is_admin and submission.submitted_by_user_id != user.id:
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
    stmt = select(CashoutDocumentAnalysis).where(
        CashoutDocumentAnalysis.cashout_document_id == document.id
    )
    analysis = (await db.execute(stmt)).scalar_one()

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
    stmt = select(CashoutDocumentAnalysis).where(
        CashoutDocumentAnalysis.cashout_document_id == document.id
    )
    analysis = (await db.execute(stmt)).scalar_one_or_none()

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
        db.add(analysis)
        await db.flush()
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
