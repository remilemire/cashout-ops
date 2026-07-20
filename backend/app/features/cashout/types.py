# backend/app/features/cashout/types.py

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.lib.documents import DocumentContentType


# PROCESSING covers the whole open phase (uploading, extracting, verifying);
# completion reconciles the verified analyses and closes the submission.
class CashoutSubmissionStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"


# The document types the AI can classify a cashout document as. UNKNOWN is the
# explicit "none of the above": the model may pick it directly, and the
# processor folds a null classification into it — so a completed analysis
# always has a classification.
class CashoutDocumentClassification(StrEnum):
    TOUCHBISTRO_SERVER_SHIFT_REPORT = "TOUCHBISTRO_SERVER_SHIFT_REPORT"
    PAYSTONE_TERMINAL_REPORT = "PAYSTONE_TERMINAL_REPORT"
    PAYMENT_RECEIPT = "PAYMENT_RECEIPT"
    DAILY_TIP_OUT_SHEET = "DAILY_TIP_OUT_SHEET"
    DAILY_CASH_SUMMARY = "DAILY_CASH_SUMMARY"
    MANUAL_NOTE = "MANUAL_NOTE"
    UNKNOWN = "UNKNOWN"


# EXTRACTING (AI running in the background — poll the analysis) →
# NEEDS_VERIFICATION (extraction produced data, awaiting the cashier) or
# FAILED (error_code/error_message set; retry via the extract endpoint) →
# VERIFIED (cashier confirmed, possibly with corrections).
class DocumentAnalysisStatus(StrEnum):
    EXTRACTING = "EXTRACTING"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DocumentUpload:
    data: bytes
    content_type: DocumentContentType
    original_filename: str
