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

from . import service as uploads_service

router = APIRouter()

UploadId = Annotated[UUID, Path(description="Cashout upload ID.")]


@router.delete(
    "/uploads/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        "UPLOAD_NOT_FOUND", "SUBMISSION_COMPLETED", "VALIDATION_FAILED"
    ),
)
async def delete_upload(
    upload_id: UploadId,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> None:
    """Remove an upload (and its analyses) from an incomplete submission.

    The submission's employee or an admin may remove uploads, and only while
    the submission is still `PROCESSING`.
    """
    await uploads_service.delete_upload(
        db,
        upload_id=upload_id,
        user=current_user,
        storage=storage,
    )


_UPLOAD_CONTENT_OK: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The original uploaded bytes.",
        "content": {member.value: {} for member in DocumentContentType},
    }
}


@router.get(
    "/uploads/{upload_id}/content",
    response_class=Response,
    responses=_UPLOAD_CONTENT_OK
    | error_responses("UPLOAD_NOT_FOUND", "VALIDATION_FAILED"),
)
async def get_upload_content(
    upload_id: UploadId,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> Response:
    """Serve the original uploaded file (image or PDF), inline.

    Accessible to the submission's employee or an admin.
    """
    upload, data = await uploads_service.get_upload_content(
        db, upload_id=upload_id, user=current_user, storage=storage
    )
    filename = upload.original_filename.replace('"', "")
    return Response(
        content=data,
        media_type=upload.content_type.value,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


__all__ = ["router"]
