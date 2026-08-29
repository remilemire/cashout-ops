# backend/app/features/cashout/analyses/schemas.py

from __future__ import annotations

import uuid
from typing import Any

from app.core.providers import AIProvider
from app.core.schemas import BaseIn, BaseOut, UtcDateTime
from app.features.cashout.extraction.types import CashoutDocumentClassification

from .types import DocumentAnalysisStatus


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


class CashoutAnalysisVerify(BaseIn):
    # Corrections to the extracted data; omit (or null) to confirm it as-is.
    verified_data: dict[str, Any] | None = None


class CashoutDocumentExtract(BaseIn):
    # A corrected classification: the rerun skips AI classification and
    # extracts as this type. Omit (or null) for an ordinary retry — a full
    # classify + extract.
    classification: CashoutDocumentClassification | None = None


__all__ = [
    "CashoutAnalysisVerify",
    "CashoutDocumentAnalysisOut",
    "CashoutDocumentExtract",
]
