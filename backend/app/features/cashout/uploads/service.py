from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError
from app.features.cashout.shared.access import ensure_can_view
from app.features.cashout.submissions.model import CashoutSubmission
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from app.features.users.model import User
from app.integrations.storage import DocumentNotFoundError, DocumentStorageClient

from . import repository
from .model import CashoutUpload
from .types import UploadPayload

logger = logging.getLogger(__name__)


async def store_upload(
    db: AsyncSession,
    *,
    payload: UploadPayload,
    submission_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> CashoutUpload:
    """Validate and store an uploaded file on an incomplete submission.

    Storage only: the AI extraction is started by the upload-intake workflow
    (`shared/workflows.py`), which calls this and then starts extraction on
    the stored upload in the same transaction.
    """
    submission = await _get_submission_for_actor(
        db, submission_id=submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Uploads cannot be added after completion."
        )

    # The router already stops reading past the limit, so this normally sees
    # the single byte of overshoot; it stays as the authoritative check for
    # callers that assembled the payload some other way.
    if len(payload.data) > settings.storage.MAX_DOCUMENT_SIZE_BYTES:
        raise AppError(
            "UPLOAD_TOO_LARGE",
            ctx={"maxSizeMb": settings.storage.MAX_DOCUMENT_SIZE_MB},
        )

    upload = CashoutUpload(
        content_type=payload.content_type,
        storage_key=f"cashout/{submission.id}/{uuid4().hex}",
        original_filename=payload.original_filename,
        checksum_sha256=hashlib.sha256(payload.data).hexdigest(),
        # The actual actor: the admin when an admin uploads for the employee.
        uploaded_by_user_id=user.id,
        uploaded_at=datetime.now(UTC),
        cashout_submission_id=submission.id,
    )

    await repository.add_upload(db, upload)
    await storage.write(upload.storage_key, payload.data)

    return upload


async def delete_upload(
    db: AsyncSession,
    *,
    upload_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> None:
    """Remove an upload (and its analyses) from an incomplete submission."""
    upload = await _get_upload(db, upload_id)
    submission = await _get_submission_for_actor(
        db, submission_id=upload.cashout_submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Uploads cannot be removed after completion."
        )

    # The original and the crop each of its analyses read all go with the row.
    storage_keys = [
        upload.storage_key,
        *await repository.list_crop_storage_keys(db, upload_id=upload.id),
    ]
    await repository.delete_upload(db, upload)
    for storage_key in storage_keys:
        await storage.delete(storage_key)


async def get_upload_content(
    db: AsyncSession,
    *,
    upload_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> tuple[CashoutUpload, bytes]:
    """The original uploaded bytes, for viewing; employee or admin."""
    upload = await _get_upload(db, upload_id)
    submission = await _get_submission(db, upload.cashout_submission_id)
    ensure_can_view(submission, user)

    try:
        data = await storage.read(upload.storage_key)
    except DocumentNotFoundError as exc:
        # The row survived but its stored bytes did not (lost or deleted out
        # of band). To the viewer the upload is gone; the mismatch itself is
        # an operational signal, so it goes to the logs.
        logger.warning(
            "Stored file missing for upload %s (key %s)",
            upload.id,
            upload.storage_key,
        )
        raise AppError("UPLOAD_NOT_FOUND", "The stored file is missing.") from exc
    return upload, data


async def _get_upload(db: AsyncSession, upload_id: UUID) -> CashoutUpload:
    upload = await repository.get_upload(db, upload_id=upload_id)
    if upload is None:
        raise AppError("UPLOAD_NOT_FOUND")
    return upload


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


__all__ = [
    "store_upload",
    "delete_upload",
    "get_upload_content",
]
