# backend/app/services/cashout.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CashoutData, CashoutDocument, CashoutSubmission

# note for claude: remove any asyncs if unnecessary. also you can create schema files in schemas/ where appropriate


async def create_submission(db: AsyncSession, *, shift_id: int) -> CashoutSubmission:
    # TODO
    # make sure to throw if shift already has submission
    ...


async def add_document(
    db: AsyncSession, *, payload: ..., submission_id: int
) -> CashoutDocument:
    # TODO
    ...


# create cashout_data, call ocr service, change status to UNDER_REVIEW if successful, FAILED otherwise
async def process_submission(
    db: AsyncSession, *, submission_id: int
) -> CashoutSubmission:  # join cashout_data
    # TODO
    ...


async def review_data(db: AsyncSession, *, payload: ..., data_id: int) -> CashoutData:
    # TODO
    ...


# change status to COMPLETE
async def complete_submission(
    db: AsyncSession, *, submission_id: CashoutSubmission
) -> CashoutSubmission:
    # TODO
    # ensure data has been reviewed
    ...
