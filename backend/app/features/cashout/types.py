# backend/app/features/cashout/types.py

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.integrations.ai import AIErrorCode
from app.lib.documents import DocumentContentType


# PROCESSING covers the whole open phase (uploading, extracting, verifying);
# completion reconciles the verified analyses and closes the submission.
class CashoutSubmissionStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"


class CashoutDocumentType(StrEnum):
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


# Analysis error codes beyond those raised by the AI layer (AIErrorCode).
class DocumentAnalysisErrorCode(StrEnum):
    UNCLASSIFIED = "UNCLASSIFIED"
    INTERNAL = "INTERNAL"


# Safe, user-facing messages keyed by the persisted error_code (AIErrorCode from
# the AI layer plus DocumentAnalysisErrorCode above). Raw provider messages are
# never surfaced on the analysis — they can leak internal/provider detail — so
# every failure maps its code to one of these. Log the raw text instead.
_ANALYSIS_ERROR_MESSAGES: dict[str, str] = {
    AIErrorCode.PROVIDER_ERROR.value: (
        "The document service is temporarily unavailable. Please try again."
    ),
    AIErrorCode.REFUSED.value: (
        "This document could not be processed. Please check it and try again."
    ),
    AIErrorCode.INVALID_RESPONSE.value: (
        "The document could not be read. Please retry or re-upload a clearer copy."
    ),
    AIErrorCode.UNSUPPORTED_CONTENT.value: (
        "This file type isn't supported. Please upload a photo or PDF."
    ),
    DocumentAnalysisErrorCode.UNCLASSIFIED.value: (
        "The document could not be classified."
    ),
    DocumentAnalysisErrorCode.INTERNAL.value: "Extraction failed unexpectedly.",
}

_DEFAULT_ANALYSIS_ERROR_MESSAGE = "Extraction failed. Please try again."


def analysis_error_message(code: str) -> str:
    """User-facing message for a persisted analysis error_code."""
    return _ANALYSIS_ERROR_MESSAGES.get(code, _DEFAULT_ANALYSIS_ERROR_MESSAGE)


@dataclass(frozen=True)
class DocumentUpload:
    data: bytes
    content_type: DocumentContentType
    original_filename: str
