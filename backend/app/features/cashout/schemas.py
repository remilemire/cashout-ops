# backend/app/features/cashout/schemas.py

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from app.core.schemas import BaseIn, BaseOut, UtcDateTime
from app.features.users.schemas import UserOut
from app.integrations.ai import AIProvider
from app.lib.documents import DocumentContentType

from .types import (
    CashoutDocumentClassification,
    CashoutSubmissionStatus,
    DocumentAnalysisStatus,
)


class CashoutSubmissionOut(BaseOut):
    id: uuid.UUID
    created_at: UtcDateTime
    status: CashoutSubmissionStatus
    submitted_by_user_id: uuid.UUID
    submitted_at: UtcDateTime


class CashoutSubmissionListOut(CashoutSubmissionOut):
    submitted_by: UserOut


class CashoutDocumentAnalysisOut(BaseOut):
    id: uuid.UUID
    created_at: UtcDateTime
    provider: AIProvider
    model: str
    status: DocumentAnalysisStatus
    classification: CashoutDocumentClassification | None = None
    classification_confidence: float | None = None
    schema_name: str | None = None
    extracted_data_json: dict[str, Any] | None = None
    extraction_confidence: float | None = None
    issues: list[dict[str, Any]] | None = None
    error_code: str | None = None
    error_message: str | None = None
    completed_at: UtcDateTime | None = None
    verified_data_json: dict[str, Any] | None = None
    verified_by_user_id: uuid.UUID | None = None
    verified_at: UtcDateTime | None = None
    cashout_document_id: uuid.UUID


class CashoutDocumentOut(BaseOut):
    id: uuid.UUID
    created_at: UtcDateTime
    content_type: DocumentContentType
    original_filename: str
    checksum_sha256: str
    uploaded_by_user_id: uuid.UUID
    uploaded_at: UtcDateTime
    cashout_submission_id: uuid.UUID
    analysis: CashoutDocumentAnalysisOut | None = None


class CashoutDataOut(BaseOut):
    id: uuid.UUID
    created_at: UtcDateTime
    # TODO(document-ai): placeholder reconciled fields; see models/data.py.
    daily_tipout: Decimal | None = None
    net_total: Decimal | None = None
    cash_total: Decimal | None = None
    card_total: Decimal | None = None
    submission_id: uuid.UUID


class CashoutSubmissionDetailOut(CashoutSubmissionOut):
    submitted_by: UserOut
    documents: list[CashoutDocumentOut]
    data: CashoutDataOut | None = None


class CashoutAnalysisVerify(BaseIn):
    # Corrections to the extracted data; omit (or null) to confirm it as-is.
    verified_data: dict[str, Any] | None = None
