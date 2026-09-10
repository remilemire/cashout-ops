from __future__ import annotations

import uuid
from typing import Any

from app.core.providers import AIProvider
from app.core.schemas import BaseIn, BaseOut, UtcDateTime
from app.features.cashout.extraction.types import CashoutDocumentClassification
from app.lib.documents import DocumentContentType

from .types import DocumentAnalysisStatus


class CashoutDocumentAnalysisOut(BaseOut):
    id: uuid.UUID
    created_at: UtcDateTime
    # Reading order among the upload's analyses (1-based): the order the
    # documents were found in the upload.
    position: int
    # Null when the current outcome was entered manually.
    provider: AIProvider | None = None
    model: str | None = None
    status: DocumentAnalysisStatus
    classification: CashoutDocumentClassification | None = None
    classification_confidence: float | None = None
    schema_name: str | None = None
    # Which shape of the named schema the extracted data follows; data written
    # under an older version keeps its shape until a re-extraction replaces it.
    schema_version: int | None = None
    extracted_data_json: dict[str, Any] | None = None
    extraction_confidence: float | None = None
    issues: list[dict[str, Any]] | None = None
    # Set when the extraction read a crop — this analysis's document among
    # those found in the upload — rather than the whole upload; the crop is
    # served by the analysis's cropped endpoint.
    cropped_content_type: DocumentContentType | None = None
    error_code: str | None = None
    error_message: str | None = None
    completed_at: UtcDateTime | None = None
    verified_data_json: dict[str, Any] | None = None
    verified_by_user_id: uuid.UUID | None = None
    verified_at: UtcDateTime | None = None
    cashout_upload_id: uuid.UUID


class CashoutAnalysisVerify(BaseIn):
    # Corrections to the extracted data; omit (or null) to confirm it as-is.
    verified_data: dict[str, Any] | None = None


class CashoutAnalysisExtract(BaseIn):
    # A corrected classification: the rerun skips AI classification and
    # extracts as this type. Omit (or null) for an ordinary retry — a full
    # classify + extract.
    classification: CashoutDocumentClassification | None = None


class CashoutDocumentManualEntry(BaseIn):
    # The document type the user asserts; its registered extraction schema is
    # what the data below is validated against.
    classification: CashoutDocumentClassification
    # The typed-in field values, validated against the classification's schema.
    # A plain dict, so nested keys pass through un-aliased: the schema's
    # snake_case field names survive as-is (matching extracted_data_json).
    data: dict[str, Any]


__all__ = [
    "CashoutAnalysisExtract",
    "CashoutAnalysisVerify",
    "CashoutDocumentAnalysisOut",
    "CashoutDocumentManualEntry",
]
