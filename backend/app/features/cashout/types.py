# backend/app/features/cashout/types.py

from __future__ import annotations

from enum import StrEnum


class CashoutSubmissionStatus(StrEnum):
    PROCESSING = "PROCESSING"
    UNDER_REVIEW = "UNDER_REVIEW"
    COMPLETED = "COMPLETED"


class CashoutDocumentType(StrEnum):
    TOUCHBISTRO_SERVER_SHIFT_REPORT = "TOUCHBISTRO_SERVER_SHIFT_REPORT"
    PAYSTONE_TERMINAL_REPORT = "PAYSTONE_TERMINAL_REPORT"
    PAYMENT_RECEIPT = "PAYMENT_RECEIPT"
    DAILY_TIP_OUT_SHEET = "DAILY_TIP_OUT_SHEET"
    DAILY_CASH_SUMMARY = "DAILY_CASH_SUMMARY"
    MANUAL_NOTE = "MANUAL_NOTE"
    UNKNOWN = "UNKNOWN"


class DocumentContentType(StrEnum):
    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"
    PDF = "application/pdf"
    HEIC = "image/heic"
    HEIF = "image/heif"


class OcrProvider(StrEnum):
    GOOGLE_VISION = "GOOGLE_VISION"


class OcrStatus(StrEnum):
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
