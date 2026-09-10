# backend/app/features/cashout/documents/router.py

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response, status

from app.errors import error_responses
from app.features.auth.dependencies import get_current_user
from app.features.users.model import User
from app.infrastructure.db.dependencies import DbSession
from app.integrations.storage import DocumentStorageClient
from app.integrations.storage.dependencies import get_document_storage
from app.lib.documents import DocumentContentType

from . import service as documents_service

router = APIRouter()

# Path parameters are UUIDs; Pydantic validates them (a malformed id → 422).
DocumentId = Annotated[UUID, Path(description="Cashout document ID.")]


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        "DOCUMENT_NOT_FOUND", "SUBMISSION_COMPLETED", "VALIDATION_FAILED"
    ),
)
async def delete_document(
    document_id: DocumentId,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> None:
    """Remove a document (and its analyses) from an incomplete submission.

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
    db: DbSession,
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


__all__ = ["router"]
