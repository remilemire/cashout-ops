# backend/app/features/cashout/service.py

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

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


# use ocr_client
async def extract_document(db: AsyncSession, *, document_id: int) -> CashoutOcrResult:
    # TODO
    ...


# reconcile cashout_data, change status to UNDER_REVIEW if successful, FAILED otherwise
async def process_submission(
    db: AsyncSession, *, submission_id: int
) -> CashoutSubmission:  # join cashout_data
    # TODO
    # each document must have successful ocr result
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


async def _reconcile_ocr_data(
    db: AsyncSession, ocr_results: Sequence[CashoutOcrResult]
) -> CashoutData:
    # TODO
    ...
