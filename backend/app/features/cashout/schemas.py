# backend/app/features/cashout/schemas.py

from __future__ import annotations

from typing import Any

from app.core.schemas import BaseIn, EntityOut, UtcDateTime
from app.integrations.ai import AIProvider
from app.lib.documents import DocumentContentType

from .types import CashoutDocumentType, CashoutSubmissionStatus, DocumentAnalysisStatus


class CashoutSubmissionOut(EntityOut):
    status: CashoutSubmissionStatus
    submitted_by_user_id: int
    submitted_at: UtcDateTime


class CashoutDocumentOut(EntityOut):
    document_type: CashoutDocumentType
    content_type: DocumentContentType
    original_filename: str
    checksum_sha256: str
    uploaded_by_user_id: int
    uploaded_at: UtcDateTime
    cashout_submission_id: int


class CashoutDocumentAnalysisOut(EntityOut):
    provider: AIProvider
    model: str
    status: DocumentAnalysisStatus
    classification: CashoutDocumentType | None = None
    classification_confidence: float | None = None
    schema_name: str | None = None
    extracted_data_json: dict[str, Any] | None = None
    extraction_confidence: float | None = None
    issues: list[dict[str, Any]] | None = None
    error_code: str | None = None
    error_message: str | None = None
    completed_at: UtcDateTime | None = None
    cashout_document_id: int


class CashoutDataOut(EntityOut):
    extracted_data_json: dict[str, Any] | None = None
    reviewed_data_json: dict[str, Any] | None = None
    reviewed_by_user_id: int | None = None
    reviewed_at: UtcDateTime | None = None
    submission_id: int


class CashoutSubmissionDetailOut(CashoutSubmissionOut):
    documents: list[CashoutDocumentOut]
    data: CashoutDataOut | None = None


class CashoutDataReview(BaseIn):
    reviewed_data: dict[str, Any]
