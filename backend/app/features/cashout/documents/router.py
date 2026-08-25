# backend/app/features/cashout/documents/router.py

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import error_responses
from app.features.auth.dependencies import get_current_user
from app.features.cashout.analyses.schemas import CashoutDocumentAnalysisOut
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.features.cashout.extraction.dependencies import (
    get_cashout_document_processor,
)
from app.features.cashout.shared import intake
from app.features.users.model import User
from app.infrastructure.db.dependencies import get_db
from app.integrations.storage import DocumentStorageClient
from app.integrations.storage.dependencies import get_document_storage
from app.lib.documents import DocumentContentType

from . import service as documents_service
from .dependencies import rate_limit_extract

router = APIRouter(prefix="/documents")

# Path parameters are UUIDs; Pydantic validates them (a malformed id → 422).
DocumentId = Annotated[UUID, Path(description="Cashout document ID.")]


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        "DOCUMENT_NOT_FOUND", "SUBMISSION_COMPLETED", "VALIDATION_FAILED"
    ),
)
async def delete_document(
    document_id: DocumentId,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> None:
    """Remove a document (and its analysis) from an incomplete submission.

    The submission's employee or an admin may remove documents, and only
    while the submission is still `PROCESSING`.
    """
    await documents_service.delete_document(
        db,
        document_id=document_id,
        user=current_user,
        storage=storage,
    )


_DOCUMENT_CONTENT_OK: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The original uploaded bytes.",
        "content": {member.value: {} for member in DocumentContentType},
    }
}


@router.get(
    "/{document_id}/content",
    response_class=Response,
    responses=_DOCUMENT_CONTENT_OK
    | error_responses("DOCUMENT_NOT_FOUND", "VALIDATION_FAILED"),
)
async def get_document_content(
    document_id: DocumentId,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> Response:
    """Serve the original uploaded document (image or PDF), inline.

    Accessible to the submission's employee or an admin.
    """
    document, data = await documents_service.get_document_content(
        db, document_id=document_id, user=current_user, storage=storage
    )
    filename = document.original_filename.replace('"', "")
    return Response(
        content=data,
        media_type=document.content_type.value,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# The URL addresses a document; the behavior belongs to analyses (shared/intake.py).
@router.post(
    "/{document_id}/extract",
    response_model=CashoutDocumentAnalysisOut,
    # Re-extraction burns provider tokens on demand — per-user quota applies.
    dependencies=[Depends(rate_limit_extract)],
    responses=error_responses(
        "DOCUMENT_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "ANALYSIS_VERIFIED",
        "EXTRACTION_IN_PROGRESS",
        "VALIDATION_FAILED",
        "RATE_LIMITED",
    ),
)
async def extract_document(
    document_id: DocumentId,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    processor: Annotated[
        CashoutDocumentProcessor, Depends(get_cashout_document_processor)
    ],
) -> CashoutDocumentAnalysisOut:
    """Restart extraction on a document (e.g. after a `FAILED` attempt).

    Resets the analysis to `EXTRACTING` and runs the AI in the background —
    poll `GET /cashout/analyses/{id}` for the outcome. A verified analysis
    cannot be re-run, nor one whose extraction is still in progress.
    """
    analysis = await intake.restart_extraction(
        db,
        document_id=document_id,
        user=current_user,
        processor=processor,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


__all__ = ["router"]
