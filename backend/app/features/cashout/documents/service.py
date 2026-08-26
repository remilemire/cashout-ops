# backend/app/features/cashout/documents/service.py

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError
from app.features.cashout.shared.access import ensure_can_view
from app.features.cashout.submissions.model import CashoutSubmission
from app.features.cashout.submissions.types import CashoutSubmissionStatus
from app.features.users.model import User
from app.integrations.storage import DocumentStorageClient

from . import repository
from .model import CashoutDocument
from .types import DocumentUpload


async def upload_document(
    db: AsyncSession,
    *,
    payload: DocumentUpload,
    submission_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> CashoutDocument:
    """Validate and store an uploaded document on an incomplete submission.

    Storage only: the AI extraction is started by the document-intake workflow
    (`shared/workflows.py`), which calls this and then starts extraction on the
    stored document in the same transaction.
    """
    submission = await _get_submission_for_actor(
        db, submission_id=submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Documents cannot be added after completion."
        )

    # The router already stops reading past the limit, so this normally sees
    # the single byte of overshoot; it stays as the authoritative check for
    # callers that assembled the payload some other way.
    if len(payload.data) > settings.storage.MAX_DOCUMENT_SIZE_BYTES:
        raise AppError("DOCUMENT_TOO_LARGE")

    document = CashoutDocument(
        content_type=payload.content_type,
        storage_key=f"cashout/{submission.id}/{uuid4().hex}",
        original_filename=payload.original_filename,
        checksum_sha256=hashlib.sha256(payload.data).hexdigest(),
        # The actual actor: the admin when an admin uploads for the employee.
        uploaded_by_user_id=user.id,
        uploaded_at=datetime.now(UTC),
        cashout_submission_id=submission.id,
    )

    await repository.add_document(db, document)
    await storage.write(document.storage_key, payload.data)

    return document


async def delete_document(
    db: AsyncSession,
    *,
    document_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> None:
    """Remove a document (and its analysis) from an incomplete submission."""
    document = await _get_document(db, document_id)
    submission = await _get_submission_for_actor(
        db, submission_id=document.cashout_submission_id, actor=user
    )
    if submission.status is not CashoutSubmissionStatus.PROCESSING:
        raise AppError(
            "SUBMISSION_COMPLETED", "Documents cannot be removed after completion."
        )

    await repository.delete_document(db, document)
    await storage.delete(document.storage_key)


async def get_document_content(
    db: AsyncSession,
    *,
    document_id: UUID,
    user: User,
    storage: DocumentStorageClient,
) -> tuple[CashoutDocument, bytes]:
    """The original uploaded bytes, for viewing; employee or admin."""
    document = await _get_document(db, document_id)
    submission = await _get_submission(db, document.cashout_submission_id)
    ensure_can_view(submission, user)

    return document, await storage.read(document.storage_key)


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


__all__ = [
    "upload_document",
    "delete_document",
    "get_document_content",
]
