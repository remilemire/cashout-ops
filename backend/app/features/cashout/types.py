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


# The document types the AI can classify a cashout document as. UNKNOWN is the
# explicit "none of the above": the model may pick it directly, and the
# processor folds a null classification into it — so a completed analysis
# always has a classification.
class CashoutDocumentClassification(StrEnum):
    TOUCHBISTRO_SERVER_SHIFT_REPORT = "touchbistro_server_shift_report"
    PAYSTONE_TERMINAL_REPORT = "paystone_terminal_report"
    PAYMENT_RECEIPT = "payment_receipt"
    DAILY_TIP_OUT_SHEET = "daily_tip_out_sheet"
    DAILY_CASH_SUMMARY = "daily_cash_summary"
    MANUAL_NOTE = "manual_note"
    UNKNOWN = "unknown"


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
