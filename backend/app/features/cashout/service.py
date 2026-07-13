# backend/app/features/cashout/service.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .extraction import CashoutDocumentProcessor
from .models import (
    CashoutData,
    CashoutDocument,
    CashoutOcrResult,
    CashoutSubmission,
)

# note for agent: remove any asyncs if unnecessary. also you can create schema files in schemas/ where appropriate


async def create_submission(db: AsyncSession, *, user_id: int) -> CashoutSubmission:
    # TODO
    # make sure to throw if shift already has submission
    ...


async def upload_document(
    db: AsyncSession, *, payload: ..., submission_id: int
) -> CashoutDocument:
    # TODO
    ...


# TODO(document-ai): Rename this operation and its persisted result away from
# OCR terminology once the model migration is designed.
async def extract_document(
    db: AsyncSession,
    *,
    document_id: int,
    processor: CashoutDocumentProcessor,
) -> CashoutOcrResult:
    # TODO(document-ai): Load the document, construct a DocumentRef from its
    # storage fields, invoke the processor, and persist the typed result without
    # committing. Update document_type only after classification succeeds.
    ...


# reconcile cashout_data, change status to UNDER_REVIEW if successful, FAILED otherwise
async def process_submission(
    db: AsyncSession, *, submission_id: int
) -> CashoutSubmission:  # join cashout_data
    # TODO
    # TODO(document-ai): Require one successful document-analysis result per
    # document before reconciling their extracted data.
    ...


async def review_data(db: AsyncSession, *, payload: ..., data_id: int) -> CashoutData:
    # TODO
    ...


# reconcile ocr data and change status to COMPLETE
async def complete_submission(
    db: AsyncSession, *, submission_id: CashoutSubmission
) -> CashoutSubmission:
    # TODO
    # ensure data has been reviewed
    ...
