# backend/app/features/cashout/analyses/service.py

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.document_ai import DocumentAIError, DocumentAIErrorCode, DocumentRef
from app.errors import AppError
from app.features.cashout.documents.model import CashoutDocument
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.features.cashout.extraction.registry import parse_manual_document_data
from app.features.cashout.extraction.schemas import CashoutDocumentSchema
from app.features.cashout.extraction.types import CashoutDocumentClassification
from app.features.cashout.shared.access import ensure_can_view
from app.features.cashout.submissions.model import CashoutSubmission
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from app.features.users.model import User
from app.infrastructure.outbox import service as outbox_service
from app.integrations.storage import DocumentNotFoundError, DocumentStorageClient
from app.lib.documents import DocumentContent

from . import repository
from .messages import analysis_error_message
from .model import CashoutDocumentAnalysis
from .schemas import CashoutAnalysisVerify
from .types import DocumentAnalysisStatus

logger = logging.getLogger(__name__)


async def start_extraction(
    db: AsyncSession,
    *,
    document: CashoutDocument,
    processor: CashoutDocumentProcessor,
    classification: CashoutDocumentClassification | None = None,
) -> CashoutDocumentAnalysis:
    """Reset the document's analysis to EXTRACTING and queue the extraction.

    The message is enqueued in the caller's transaction, so it dispatches only
    once that transaction commits; the AI extraction itself runs from the
    outbox (`run_extraction` via the extraction handler). Clients poll the
    returned analysis. A supplied `classification` (a user correcting the AI)
    rides the message: the extraction skips AI classification and its
    confidence is recorded as null.
    """
    analysis = await _reset_analysis(db, document=document, processor=processor)
    await outbox_service.enqueue(
        db,
        type="cashout.run_extraction",
        payload={
            "document_id": str(document.id),
            # The enum's string value; the handler's model parses it back.
            "classification": None if classification is None else classification.value,
        },
    )
    return analysis


async def restart_extraction(
    db: AsyncSession,
    *,
    document_id: UUID,
    user: User,
    processor: CashoutDocumentProcessor,
    classification: CashoutDocumentClassification | None = None,
) -> CashoutDocumentAnalysis:
    """Reset a document's analysis and queue a fresh extraction attempt.

    As with upload, the extraction message is enqueued in this transaction
    and dispatches once the request commits. Verified analyses cannot be
    re-run, and an extraction already in flight cannot be restarted. A
    supplied `classification` skips AI classification and extracts straight
    into that type's schema, recording a null classification confidence.
    """
    document = await _get_document(db, document_id)
    submission = await _get_submission_for_actor(
        db, submission_id=document.cashout_submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Documents cannot be analyzed after completion."
        )

    return await start_extraction(
        db, document=document, processor=processor, classification=classification
    )


async def record_manual_entry(
    db: AsyncSession,
    *,
    document: CashoutDocument,
    classification: CashoutDocumentClassification,
    data: CashoutDocumentSchema,
    user: User,
) -> CashoutDocumentAnalysis:
    """Record a manually entered analysis: no AI involved, directly VERIFIED.

    Typing the values is the verification, so the analysis lands VERIFIED with
    the actor as its verifier. The validated entry is written to both the
    extracted and verified data, so unverify → edit → re-verify (and a later
    retry extraction) behave exactly as they do after an AI run. A null
    provider/model is what marks the analysis as manual.
    """
    analysis = await repository.find_analysis_by_document(db, document_id=document.id)
    _ensure_replaceable(analysis)

    if analysis is None:
        analysis = CashoutDocumentAnalysis(cashout_document_id=document.id)
        await repository.add_analysis(db, analysis)

    now = datetime.now(UTC)
    dumped = data.model_dump(mode="json")

    # The AI-run fields are nulled explicitly: when a FAILED or unverified
    # analysis is converted, its old provider/confidence/error state must not
    # survive under the manual entry. The crop (cropped_*) is not among them:
    # it describes the document, not the run, and the card keeps previewing
    # it.
    analysis.provider = None
    analysis.model = None
    analysis.status = DocumentAnalysisStatus.VERIFIED
    analysis.classification = classification
    analysis.classification_confidence = None
    analysis.schema_name = type(data).__name__
    analysis.schema_version = type(data).SCHEMA_VERSION
    analysis.extracted_data_json = dumped
    analysis.extraction_confidence = None
    analysis.issues = None
    analysis.error_code = None
    analysis.error_message = None
    analysis.completed_at = now
    analysis.verified_data_json = dumped
    analysis.verified_by_user_id = user.id
    analysis.verified_at = now
    return analysis


async def replace_with_manual_entry(
    db: AsyncSession,
    *,
    document_id: UUID,
    classification: CashoutDocumentClassification,
    data: dict[str, Any],
    user: User,
) -> CashoutDocumentAnalysis:
    """Replace a document's analysis outcome with a manually entered one.

    The entered data is validated against the classification's registered
    schema before anything else happens. Allowed from FAILED and
    NEEDS_VERIFICATION: a verified analysis cannot be replaced, nor one whose
    extraction is still in flight.
    """
    parsed = parse_manual_document_data(classification, data)

    document = await _get_document(db, document_id)
    submission = await _get_submission_for_actor(
        db, submission_id=document.cashout_submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Documents cannot be analyzed after completion."
        )

    return await record_manual_entry(
        db, document=document, classification=classification, data=parsed, user=user
    )


async def run_extraction(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    document_id: UUID,
    processor: CashoutDocumentProcessor,
    classification: CashoutDocumentClassification | None = None,
) -> None:
    """Outbox job: run the AI extraction and persist the outcome.

    Runs from the extraction handler after the upload/extract request has
    committed its EXTRACTING analysis, so it owns its session and
    transaction — the one sanctioned exception to "services never commit".
    All failures are handled here (the analysis is marked FAILED), so the
    outbox message completes even when the extraction does not. A supplied
    `classification` skips AI classification (its confidence is recorded as
    null).
    """
    async with sessionmaker() as db:
        try:
            document = await repository.get_document(db, document_id=document_id)
            if document is None:
                # Deleted between the request committing and this job running;
                # the cascade removed its analysis too — nothing to update.
                return
            submission = await repository.get_live_submission(
                db, submission_id=document.cashout_submission_id
            )
            if submission is None:
                # The submission was cancelled (soft-deleted) after the
                # extraction was enqueued. The document and its analysis
                # survive but nothing can reach them anymore, so skip the AI
                # call rather than analyzing a dead cashout.
                return
            await _apply_extraction(
                db,
                document=document,
                processor=processor,
                classification=classification,
            )
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


async def get_cropped_document(
    db: AsyncSession,
    *,
    analysis_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> tuple[DocumentContent, str]:
    """The crop this analysis read, with the document's filename, for
    viewing; employee or admin.

    An analysis that read the document whole has no crop and is, to this
    endpoint, not found: the caller already knows from
    `cropped_content_type` whether to ask.
    """
    analysis = await _get_analysis(db, analysis_id)

    document = await _get_document(db, analysis.cashout_document_id)
    submission = await _get_submission(db, document.cashout_submission_id)
    ensure_can_view(submission, user)

    storage_key = analysis.cropped_storage_key
    content_type = analysis.cropped_content_type
    if storage_key is None or content_type is None:
        raise AppError("DOCUMENT_NOT_FOUND", "This analysis has no cropped document.")
    try:
        data = await storage.read(storage_key)
    except DocumentNotFoundError as exc:
        # The row outlived its stored bytes (lost or deleted out of band). To
        # the viewer the crop is gone; the mismatch is an operational signal.
        logger.warning(
            "Stored crop missing for analysis %s (key %s)", analysis.id, storage_key
        )
        raise AppError("DOCUMENT_NOT_FOUND", "The stored crop is missing.") from exc
    content = DocumentContent(data=data, content_type=content_type)
    return content, document.original_filename


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

    Editing a verified extraction means re-verifying it: the verifier and
    timestamp are cleared and the analysis returns to NEEDS_VERIFICATION,
    while the extraction fields stay untouched so the verification form
    re-renders from them. The verified data is preserved so corrections made
    on the first pass seed the re-edit instead of being dropped. Combined
    with unsubmit, this is how an admin corrects an already-completed
    cashout.
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
    classification: CashoutDocumentClassification | None = None,
) -> None:
    """Crop, then run classification + extraction, and persist the outcome.

    The first extraction crops the document to its printed area and records
    the crop on the analysis; it and every rerun then read that crop rather
    than the whole image. Success lands the analysis in NEEDS_VERIFICATION
    with its extracted data. A document the AI cannot place, like a provider
    failure, lands it in FAILED with error_code/error_message — there is
    nothing to verify either way, so the cashier retries, replaces the
    document, or enters its details manually. A supplied `classification` is
    passed to the processor, which skips the AI classify step and reports a
    null classification confidence.
    """
    analysis = await repository.find_analysis_by_document(db, document_id=document.id)
    if analysis is None:
        # Unreachable in practice: the reset created the row before this ran.
        raise RuntimeError("analysis missing for document under extraction")

    original = DocumentRef(
        storage_key=document.storage_key, content_type=document.content_type
    )
    if analysis.cropped_storage_key is None:
        # No crop yet — the first run, or earlier runs found nothing to crop
        # to. Trying again on a rerun is cheap and picks up a detector or a
        # setting that has changed since; a crop, once made, is kept. Recorded
        # before the AI call so a failed extraction still keeps its crop.
        crop = await processor.crop(original)
        if crop is not None:
            analysis.cropped_storage_key = crop.storage_key
            analysis.cropped_content_type = crop.content_type
            analysis.crop_bounds = crop.bounds.as_json()
    ref = _extraction_source(analysis, original)

    try:
        result = await processor.process(ref, classification=classification)
    except DocumentAIError as exc:
        # Persist the code + a safe mapped message; the raw provider text can
        # leak internal detail, so keep it in the logs only. An unclassifiable
        # document is an expected outcome of the flow, not an operational
        # fault — logged as info, where provider failures warrant a warning.
        log = (
            logger.info
            if exc.code is DocumentAIErrorCode.UNCLASSIFIABLE_DOCUMENT
            else logger.warning
        )
        log(
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
    analysis.schema_name = result.schema_name
    analysis.schema_version = result.schema_version
    analysis.extracted_data_json = result.data.model_dump(mode="json")
    analysis.extraction_confidence = result.confidence
    analysis.issues = [issue.model_dump(mode="json") for issue in result.issues]


def _extraction_source(
    analysis: CashoutDocumentAnalysis, original: DocumentRef
) -> DocumentRef:
    """What the AI reads: the crop recorded on the analysis, else the original."""
    if (
        analysis.cropped_storage_key is not None
        and analysis.cropped_content_type is not None
    ):
        return DocumentRef(
            storage_key=analysis.cropped_storage_key,
            content_type=analysis.cropped_content_type,
        )
    return original


def _ensure_replaceable(analysis: CashoutDocumentAnalysis | None) -> None:
    """A verified analysis is settled and one mid-extraction is owned by the
    running job: neither can be reset for a retry or overwritten manually."""
    if analysis is None:
        return
    if analysis.status is DocumentAnalysisStatus.VERIFIED:
        raise AppError("ANALYSIS_VERIFIED", "This document has already been verified.")
    if analysis.status is DocumentAnalysisStatus.EXTRACTING:
        raise AppError("EXTRACTION_IN_PROGRESS")


async def _reset_analysis(
    db: AsyncSession,
    *,
    document: CashoutDocument,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    """Create the document's analysis row, or reset it in place for a retry."""
    analysis = await repository.find_analysis_by_document(db, document_id=document.id)
    _ensure_replaceable(analysis)

    if analysis is None:
        analysis = CashoutDocumentAnalysis(
            provider=processor.provider,
            model=processor.model,
            cashout_document_id=document.id,
        )
        await repository.add_analysis(db, analysis)
        return analysis

    # The crop (cropped_*) survives the reset: it describes the document,
    # not the run, and the rerun reads it rather than detecting again.
    analysis.provider = processor.provider
    analysis.model = processor.model
    analysis.status = DocumentAnalysisStatus.EXTRACTING
    analysis.classification = None
    analysis.classification_confidence = None
    analysis.schema_name = None
    analysis.schema_version = None
    analysis.extracted_data_json = None
    analysis.extraction_confidence = None
    analysis.issues = None
    analysis.error_code = None
    analysis.error_message = None
    analysis.completed_at = None
    # Unverify preserves verified_data_json as the seed for a re-edit, so an
    # unverified analysis can carry corrections here. They were made against
    # the previous extraction: a fresh one must not be seeded from them.
    analysis.verified_data_json = None
    analysis.verified_by_user_id = None
    analysis.verified_at = None
    return analysis


__all__ = [
    "start_extraction",
    "restart_extraction",
    "record_manual_entry",
    "replace_with_manual_entry",
    "run_extraction",
    "get_analysis",
    "get_cropped_document",
    "verify_analysis",
    "unverify_analysis",
]
