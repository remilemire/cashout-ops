# backend/app/features/cashout/documents/schemas.py

from __future__ import annotations

import uuid

from app.core.schemas import BaseOut, UtcDateTime
from app.features.cashout.analyses.schemas import CashoutDocumentAnalysisOut
from app.lib.documents import DocumentContentType


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


__all__ = ["CashoutDocumentOut"]
