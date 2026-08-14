# backend/app/features/cashout/types.py

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.lib.documents import DocumentContentType


# PROCESSING covers the whole open phase (uploading, extracting, verifying);
# completion reconciles the verified analyses and closes the submission.
class CashoutSubmissionStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"


# EXTRACTING (AI running in the background — poll the analysis) →
# NEEDS_VERIFICATION (extraction produced data, awaiting the cashier) or
# FAILED (error_code/error_message set; retry via the extract endpoint) →
# VERIFIED (cashier confirmed, possibly with corrections).
class DocumentAnalysisStatus(StrEnum):
    EXTRACTING = "extracting"
    NEEDS_VERIFICATION = "needs_verification"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass(frozen=True)
class DocumentUpload:
    data: bytes
    content_type: DocumentContentType
    original_filename: str
