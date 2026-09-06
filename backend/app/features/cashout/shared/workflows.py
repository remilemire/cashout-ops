# backend/app/features/cashout/shared/workflows.py

"""Cross-sub-feature workflows: receiving a document and recording its analysis.

Document intake and entry span two sub-features — documents stores the file,
analyses records the outcome (an AI extraction, or a manual entry that skips
AI entirely) — so the workflows live here: neither sub-feature's service
depends on the other, and the namespace root's router makes a single call.
Every route that enqueues `cashout.run_extraction` enters through this module,
as do the manual entry points that enqueue nothing. Only the root router calls
it; sub-feature modules never import it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.features.cashout.analyses import service as analyses_service
from app.features.cashout.documents import service as documents_service
from app.features.cashout.extraction.registry import parse_manual_document_data

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.document_ai import DocumentCropper
    from app.features.cashout.analyses.model import CashoutDocumentAnalysis
    from app.features.cashout.documents.types import DocumentUpload
    from app.features.cashout.extraction import CashoutDocumentProcessor
    from app.features.cashout.extraction.types import CashoutDocumentClassification
    from app.features.users.model import User
    from app.integrations.storage import DocumentStorageClient


async def upload_document(
    db: AsyncSession,
    *,
    payload: DocumentUpload,
    submission_id: UUID,
    user: User,
    storage: DocumentStorageClient,
    cropper: DocumentCropper,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    """Store the document, create its EXTRACTING analysis, and queue extraction.

    The AI extraction itself runs from the outbox (`run_extraction` via the
    extraction handler); the message is enqueued in this transaction, so it
    dispatches only once the upload commits. Clients poll the returned
    analysis. The upload is cropped to its printed area on the way in (when
    text detection finds one), and the extraction reads that crop.
    """
    document = await documents_service.upload_document(
        db,
        payload=payload,
        submission_id=submission_id,
        user=user,
        storage=storage,
        cropper=cropper,
    )
    return await analyses_service.start_extraction(
        db, document=document, processor=processor
    )


async def upload_manual_document(
    db: AsyncSession,
    *,
    payload: DocumentUpload,
    submission_id: UUID,
    classification: CashoutDocumentClassification,
    data: dict[str, Any],
    user: User,
    storage: DocumentStorageClient,
    cropper: DocumentCropper,
) -> CashoutDocumentAnalysis:
    """Store the document and record its manually entered, VERIFIED analysis.

    No AI runs and nothing is enqueued: typing the values is the verification,
    so the returned analysis is already VERIFIED and there is nothing to poll.
    The entered data is validated before the upload — validating after it
    would orphan a stored blob when the transaction rolls back. The document
    is cropped like an extracting upload, so it previews the same way.
    """
    parsed = parse_manual_document_data(classification, data)
    document = await documents_service.upload_document(
        db,
        payload=payload,
        submission_id=submission_id,
        user=user,
        storage=storage,
        cropper=cropper,
    )
    return await analyses_service.record_manual_entry(
        db, document=document, classification=classification, data=parsed, user=user
    )


async def restart_extraction(
    db: AsyncSession,
    *,
    document_id: UUID,
    user: User,
    processor: CashoutDocumentProcessor,
    classification: CashoutDocumentClassification | None = None,
) -> CashoutDocumentAnalysis:
    # Pure delegation: the behavior lives wholly in the analyses service. The
    # indirection is kept so both extraction entry points enter through this
    # workflow and the root router never reaches into sub-feature services.
    return await analyses_service.restart_extraction(
        db,
        document_id=document_id,
        user=user,
        processor=processor,
        classification=classification,
    )


async def enter_manual_document(
    db: AsyncSession,
    *,
    document_id: UUID,
    classification: CashoutDocumentClassification,
    data: dict[str, Any],
    user: User,
) -> CashoutDocumentAnalysis:
    # Pure delegation: the behavior lives wholly in the analyses service. The
    # indirection is kept so every document intake/entry route enters through
    # this workflow and the root router never reaches into sub-feature
    # services.
    return await analyses_service.replace_with_manual_entry(
        db,
        document_id=document_id,
        classification=classification,
        data=data,
        user=user,
    )


__all__ = [
    "upload_document",
    "upload_manual_document",
    "restart_extraction",
    "enter_manual_document",
]
