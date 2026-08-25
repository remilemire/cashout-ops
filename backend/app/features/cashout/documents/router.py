# backend/app/features/cashout/documents/router.py

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError, error_responses
from app.features.auth.dependencies import get_current_user
from app.features.cashout.analyses.schemas import CashoutDocumentAnalysisOut
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.features.cashout.extraction.dependencies import (
    get_cashout_document_processor,
)
from app.features.users.model import User
from app.infrastructure.db.dependencies import get_db
from app.integrations.storage import DocumentStorageClient
from app.integrations.storage.dependencies import get_document_storage
from app.lib.documents import DocumentContentType, read_document

from . import service as documents_service
from .dependencies import rate_limit_upload
from .types import DocumentUpload

router = APIRouter()

# Path parameters are UUIDs; Pydantic validates them (a malformed id → 422).
SubmissionId = Annotated[UUID, Path(description="Cashout submission ID.")]
DocumentId = Annotated[UUID, Path(description="Cashout document ID.")]


@router.post(
    "/submissions/{submission_id}/documents",
    response_model=CashoutDocumentAnalysisOut,
    status_code=status.HTTP_201_CREATED,
    # Each upload starts an AI extraction, so it draws on the per-user quota.
    dependencies=[Depends(rate_limit_upload)],
    responses=error_responses(
        "UNSUPPORTED_DOCUMENT_TYPE",
        "DOCUMENT_TOO_LARGE",
        "DOCUMENT_DUPLICATE",
        "SUBMISSION_NOT_FOUND",
        "SUBMISSION_COMPLETED",
        "VALIDATION_FAILED",
        "RATE_LIMITED",
    ),
)
async def upload_document(
    submission_id: SubmissionId,
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
    processor: Annotated[
        CashoutDocumentProcessor, Depends(get_cashout_document_processor)
    ],
) -> CashoutDocumentAnalysisOut:
    """Upload an end-of-shift document and start its extraction.

    Accepts JPEG, PNG, WebP, or PDF within the configured size limit
    (`STORAGE_MAX_DOCUMENT_SIZE_MB`); a file already uploaded to this submission (same
    checksum) is rejected. The AI extraction runs in the background: this
    returns the analysis in `EXTRACTING`; poll `GET /cashout/analyses/{id}`
    until it reaches `NEEDS_VERIFICATION` or `FAILED` (retry via the extract
    endpoint).

    The content type is checked before the body is read, and the body itself is
    read only up to the limit (plus the byte that proves it was exceeded); the
    service rejects it from there.
    """
    # Resolved first so an unsupported type is rejected without reading the
    # document: keyword arguments evaluate in order, so this cannot be inlined
    # below `data` without reading the body of a file we are about to refuse.
    content_type = _to_content_type(file.content_type)
    payload = DocumentUpload(
        data=await read_document(file, limit=settings.storage.MAX_DOCUMENT_SIZE_BYTES),
        content_type=content_type,
        original_filename=file.filename or "upload",
    )
    analysis = await documents_service.upload_document(
        db,
        payload=payload,
        submission_id=submission_id,
        user=current_user,
        storage=storage,
        processor=processor,
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


@router.delete(
    "/documents/{document_id}",
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
    "/documents/{document_id}/content",
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


def _to_content_type(content_type: str | None) -> DocumentContentType:
    try:
        return DocumentContentType(content_type or "")
    except ValueError:
        raise AppError(
            "UNSUPPORTED_DOCUMENT_TYPE",
            f"Unsupported document content type: {content_type!r}.",
        ) from None


__all__ = ["router"]
