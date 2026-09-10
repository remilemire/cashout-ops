# backend/app/features/cashout/shared/workflows.py

"""Cross-sub-feature workflows: receiving an upload and recording its analyses.

Upload intake and manual entry span two sub-features — uploads stores the
file, analyses records the outcomes (an AI extraction per document found in
the upload, or a manual entry that skips AI entirely) — so the workflows live
here: neither sub-feature's service depends on the other, and the namespace
root's router makes a single call. Every route that enqueues
`cashout.run_extraction` enters through this module, as do the manual entry
points that enqueue nothing. Only the root router calls it; sub-feature
modules never import it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.features.cashout.analyses import service as analyses_service
from app.features.cashout.extraction.registry import parse_manual_document_data
from app.features.cashout.uploads import service as uploads_service

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.features.cashout.analyses.model import CashoutDocumentAnalysis
    from app.features.cashout.extraction import CashoutDocumentProcessor
    from app.features.cashout.extraction.types import CashoutDocumentClassification
    from app.features.cashout.uploads.types import UploadPayload
    from app.features.users.model import User
    from app.integrations.storage import DocumentStorageClient


async def create_upload(
    db: AsyncSession,
    *,
    payload: UploadPayload,
    submission_id: UUID,
    user: User,
    storage: DocumentStorageClient,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    """Store the upload, create its first EXTRACTING analysis, and queue
    extraction.

    The AI extraction itself runs from the outbox (`run_extraction` via the
    extraction handler); the message is enqueued in this transaction, so it
    dispatches only once the upload commits. That job also finds every
    document printed in the upload and adds an analysis for each further one.
    Clients poll the returned analysis and refresh the submission for the
    rest.
    """
    upload = await uploads_service.store_upload(
        db,
        payload=payload,
        submission_id=submission_id,
        user=user,
        storage=storage,
    )
    return await analyses_service.start_extraction(
        db, upload=upload, processor=processor, storage=storage
    )


async def create_manual_upload(
    db: AsyncSession,
    *,
    payload: UploadPayload,
    submission_id: UUID,
    classification: CashoutDocumentClassification,
    data: dict[str, Any],
    user: User,
    storage: DocumentStorageClient,
) -> CashoutDocumentAnalysis:
    """Store the upload and record its manually entered, VERIFIED analysis.

    No AI runs and nothing is enqueued: typing the values is the verification,
    so the returned analysis is already VERIFIED and there is nothing to poll.
    The entered data is validated before the upload is stored — validating
    after it would orphan a stored blob when the transaction rolls back.
    """
    parsed = parse_manual_document_data(classification, data)
    upload = await uploads_service.store_upload(
        db,
        payload=payload,
        submission_id=submission_id,
        user=user,
        storage=storage,
    )
    return await analyses_service.record_manual_entry(
        db, upload=upload, classification=classification, data=parsed, user=user
    )


async def restart_extraction(
    db: AsyncSession,
    *,
    upload_id: UUID,
    user: User,
    processor: CashoutDocumentProcessor,
    storage: DocumentStorageClient,
) -> CashoutDocumentAnalysis:
    # Pure delegation: the behavior lives wholly in the analyses service. The
    # indirection is kept so every extraction entry point enters through this
    # workflow and the root router never reaches into sub-feature services.
    return await analyses_service.restart_extraction(
        db,
        upload_id=upload_id,
        user=user,
        processor=processor,
        storage=storage,
    )


async def retry_extraction(
    db: AsyncSession,
    *,
    analysis_id: UUID,
    user: User,
    processor: CashoutDocumentProcessor,
    classification: CashoutDocumentClassification | None = None,
) -> CashoutDocumentAnalysis:
    # Pure delegation, as above.
    return await analyses_service.retry_extraction(
        db,
        analysis_id=analysis_id,
        user=user,
        processor=processor,
        classification=classification,
    )


async def replace_with_manual_entry(
    db: AsyncSession,
    *,
    analysis_id: UUID,
    classification: CashoutDocumentClassification,
    data: dict[str, Any],
    user: User,
) -> CashoutDocumentAnalysis:
    # Pure delegation: the behavior lives wholly in the analyses service. The
    # indirection is kept so every upload intake/entry route enters through
    # this workflow and the root router never reaches into sub-feature
    # services.
    return await analyses_service.replace_with_manual_entry(
        db,
        analysis_id=analysis_id,
        classification=classification,
        data=data,
        user=user,
    )


__all__ = [
    "create_upload",
    "create_manual_upload",
    "restart_extraction",
    "retry_extraction",
    "replace_with_manual_entry",
]
