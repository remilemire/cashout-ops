# backend/app/features/cashout/shared/intake.py

"""The document-intake workflow: receiving a document and getting it analyzed.

That workflow spans two sub-features — documents stores the file, analyses
extracts it — so it lives here: neither sub-feature's service depends on the
other, and routers make a single call. Every route that enqueues
`cashout.run_extraction` enters through this module. Only routers call it;
services never import it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.features.cashout.analyses import service as analyses_service
from app.features.cashout.documents import service as documents_service

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.features.cashout.analyses.model import CashoutDocumentAnalysis
    from app.features.cashout.documents.types import DocumentUpload
    from app.features.cashout.extraction import CashoutDocumentProcessor
    from app.features.users.model import User
    from app.integrations.storage import DocumentStorageClient


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
    document = await documents_service.upload_document(
        db,
        payload=payload,
        submission_id=submission_id,
        user=user,
        storage=storage,
    )
    return await analyses_service.start_extraction(
        db, document=document, processor=processor
    )


async def restart_extraction(
    db: AsyncSession,
    *,
    document_id: UUID,
    user: User,
    processor: CashoutDocumentProcessor,
) -> CashoutDocumentAnalysis:
    # Pure delegation: the behavior lives wholly in the analyses service. It
    # enters here because the documents router owns the URL, and routers call
    # their own sub-feature's service or shared/ — never a sibling's service.
    return await analyses_service.restart_extraction(
        db, document_id=document_id, user=user, processor=processor
    )


__all__ = ["upload_document", "restart_extraction"]
