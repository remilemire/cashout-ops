# backend/app/features/cashout/service.py

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
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
from .schemas import CashoutAnalysisVerify
from .types import (
    CashoutSubmissionStatus,
    DocumentAnalysisErrorCode,
    DocumentAnalysisStatus,
    DocumentUpload,
    analysis_error_message,
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
        raise NotFoundError("Cashout submission not found.")

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
    if user.role != UserRole.ADMIN:
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
        raise InvalidStateError("This cashout has already been completed.")

    stmt = (
        select(CashoutDocument)
        .options(joinedload(CashoutDocument.analysis))
        .where(CashoutDocument.cashout_submission_id == submission.id)
    )
    documents = (await db.execute(stmt)).scalars().all()
    if not documents:
        raise InvalidStateError("Upload at least one document before completing.")

    analyses: list[CashoutDocumentAnalysis] = []
    for document in documents:
        analysis = document.analysis
        if analysis is None or analysis.status is not DocumentAnalysisStatus.VERIFIED:
            raise InvalidStateError(
                "Every document must be verified before completing."
            )
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
) -> CashoutDocumentAnalysis:
    """Store the document and create its EXTRACTING analysis.

    The AI extraction itself runs in a background task (`run_extraction`)
    scheduled by the router; clients poll the returned analysis.
    """
    submission = await _get_owned_submission(
        db, submission_id=submission_id, user_id=user_id
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise InvalidStateError("Documents cannot be added after completion.")

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

    return await _reset_analysis(db, document=document, processor=processor)


async def get_document_content(
    db: AsyncSession,
    *,
    document_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> tuple[CashoutDocument, bytes]:
    """The original uploaded bytes, for viewing; owner or admin."""
    document = await CashoutDocument.get_active(db, document_id)
    submission = await CashoutSubmission.get_active(db, document.cashout_submission_id)
    _ensure_can_view(submission, user)

    return document, await storage.read(document.storage_key)


async def extract_document(
    db: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    """Reset a document's analysis for a fresh extraction attempt.

    As with upload, the extraction itself runs in the router-scheduled
    background task. Verified analyses cannot be re-run, and an extraction
    already in flight cannot be restarted.
    """
    document = await CashoutDocument.get_active(db, document_id)
    submission = await _get_owned_submission(
        db, submission_id=document.cashout_submission_id, user_id=user_id
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise InvalidStateError("Documents cannot be analyzed after completion.")

    return await _reset_analysis(db, document=document, processor=processor)


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
            document = await CashoutDocument.get_active(db, document_id)
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
            analysis.status = DocumentAnalysisStatus.FAILED
            analysis.error_code = DocumentAnalysisErrorCode.INTERNAL.value
            analysis.error_message = analysis_error_message(
                DocumentAnalysisErrorCode.INTERNAL.value
            )
            analysis.completed_at = datetime.now(UTC)
            await db.commit()


# ================================
# ---------- Analyses ------------
# ================================


async def get_analysis(
    db: AsyncSession, *, analysis_id: UUID, user: User
) -> CashoutDocumentAnalysis:
    """Poll target for extraction progress; owner or admin."""
    analysis = await CashoutDocumentAnalysis.get_active(db, analysis_id)

    document = await CashoutDocument.get_active(db, analysis.cashout_document_id)
    submission = await CashoutSubmission.get_active(db, document.cashout_submission_id)
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
    analysis = await CashoutDocumentAnalysis.get_active(db, analysis_id)

    document = await CashoutDocument.get_active(db, analysis.cashout_document_id)
    submission = await _get_owned_submission(
        db, submission_id=document.cashout_submission_id, user_id=user_id
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise InvalidStateError("This cashout has already been completed.")

    if analysis.status is DocumentAnalysisStatus.VERIFIED:
        raise InvalidStateError("This analysis has already been verified.")
    if analysis.status is DocumentAnalysisStatus.EXTRACTING:
        raise InvalidStateError("The extraction is still in progress.")
    if analysis.status is DocumentAnalysisStatus.FAILED:
        raise InvalidStateError("The extraction failed; retry it before verifying.")

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


async def _get_owned_submission(
    db: AsyncSession, *, submission_id: UUID, user_id: UUID
) -> CashoutSubmission:
    submission = await CashoutSubmission.get_active(db, submission_id)
    if submission.submitted_by_user_id != user_id:
        raise ForbiddenError("You do not have access to this cashout submission.")
    return submission


def _ensure_can_view(submission: CashoutSubmission, user: User) -> None:
    if user.role != UserRole.ADMIN and submission.submitted_by_user_id != user.id:
        raise ForbiddenError("You do not have access to this cashout submission.")


async def _apply_extraction(
    db: AsyncSession,
    *,
    document: CashoutDocument,
    processor: CashoutDocumentProcessor,
) -> None:
    """Run classification + extraction and persist the outcome on the analysis.

    Success lands the analysis in NEEDS_VERIFICATION; a provider failure or an
    unclassifiable document lands it in FAILED with error_code/error_message.
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

    analysis.classification = result.classification.value
    analysis.classification_confidence = result.classification.confidence
    analysis.completed_at = datetime.now(UTC)

    if result.data is None:
        analysis.status = DocumentAnalysisStatus.FAILED
        analysis.error_code = DocumentAnalysisErrorCode.UNCLASSIFIED.value
        analysis.error_message = analysis_error_message(
            DocumentAnalysisErrorCode.UNCLASSIFIED.value
        )
    else:
        analysis.status = DocumentAnalysisStatus.NEEDS_VERIFICATION
        analysis.schema_name = result.schema_name
        analysis.extracted_data_json = result.data.model_dump(mode="json")
        analysis.extraction_confidence = result.confidence
        analysis.issues = [issue.model_dump(mode="json") for issue in result.issues]
        document.document_type = result.classification.value


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
            raise InvalidStateError("This document has already been verified.")
        if analysis.status is DocumentAnalysisStatus.EXTRACTING:
            raise InvalidStateError("An extraction is already in progress.")

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
