# backend/app/features/cashout/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_cashout_document_processor,
    get_current_user,
    get_db,
    get_document_storage,
    require_admin,
    require_csrf,
)
from app.errors import BadRequestError
from app.features.users.model import User
from app.integrations.storage import DocumentStorageClient
from app.lib.documents import DocumentContentType

from . import service as cashout_service
from .extraction import CashoutDocumentProcessor
from .schemas import (
    CashoutDataOut,
    CashoutDataReview,
    CashoutDocumentAnalysisOut,
    CashoutDocumentOut,
    CashoutSubmissionDetailOut,
    CashoutSubmissionOut,
)
from .types import DocumentUpload

router = APIRouter(
    prefix="/cashouts",
    tags=["cashout"],
    dependencies=[Depends(require_csrf), Depends(get_current_user)],
)


# ================================
# --------- Submissions ----------
# ================================


@router.post("", response_model=CashoutSubmissionOut)
async def create_submission(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutSubmissionOut:
    submission = await cashout_service.create_submission(db, user_id=current_user.id)
    return CashoutSubmissionOut.model_validate(submission)


@router.get("/{submission_id}", response_model=CashoutSubmissionDetailOut)
async def get_submission(
    submission_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutSubmissionDetailOut:
    submission = await cashout_service.get_submission(
        db, submission_id=submission_id, user=current_user
    )
    return CashoutSubmissionDetailOut.model_validate(submission)


@router.post("/{submission_id}/process", response_model=CashoutSubmissionOut)
async def process_submission(
    submission_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutSubmissionOut:
    submission = await cashout_service.process_submission(
        db, submission_id=submission_id, user_id=current_user.id
    )
    return CashoutSubmissionOut.model_validate(submission)


@router.post(
    "/{submission_id}/complete",
    response_model=CashoutSubmissionOut,
    dependencies=[Depends(require_admin)],
)
async def complete_submission(
    submission_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CashoutSubmissionOut:
    submission = await cashout_service.complete_submission(
        db, submission_id=submission_id
    )
    return CashoutSubmissionOut.model_validate(submission)


# ================================
# ---------- Documents -----------
# ================================


@router.post("/{submission_id}/documents", response_model=CashoutDocumentOut)
async def upload_document(
    submission_id: int,
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[DocumentStorageClient, Depends(get_document_storage)],
) -> CashoutDocumentOut:
    payload = DocumentUpload(
        data=await file.read(),
        content_type=_to_content_type(file.content_type),
        original_filename=file.filename or "upload",
    )
    document = await cashout_service.upload_document(
        db,
        payload=payload,
        submission_id=submission_id,
        user_id=current_user.id,
        storage=storage,
    )
    return CashoutDocumentOut.model_validate(document)


@router.post(
    "/documents/{document_id}/extract", response_model=CashoutDocumentAnalysisOut
)
async def extract_document(
    document_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    processor: Annotated[
        CashoutDocumentProcessor, Depends(get_cashout_document_processor)
    ],
) -> CashoutDocumentAnalysisOut:
    analysis = await cashout_service.extract_document(
        db, document_id=document_id, user_id=current_user.id, processor=processor
    )
    return CashoutDocumentAnalysisOut.model_validate(analysis)


# ================================
# ------------- Data -------------
# ================================


@router.patch(
    "/data/{data_id}",
    response_model=CashoutDataOut,
    dependencies=[Depends(require_admin)],
)
async def review_data(
    data_id: int,
    payload: CashoutDataReview,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CashoutDataOut:
    data = await cashout_service.review_data(
        db, payload=payload, data_id=data_id, user_id=current_user.id
    )
    return CashoutDataOut.model_validate(data)


def _to_content_type(content_type: str | None) -> DocumentContentType:
    try:
        return DocumentContentType(content_type or "")
    except ValueError:
        supported = ", ".join(member.value for member in DocumentContentType)
        raise BadRequestError(
            f"Unsupported document content type. Supported types: {supported}."
        ) from None
