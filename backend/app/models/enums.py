# backend/app/models/enums.py

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    CASHIER = "CASHIER"
    ADMIN = "ADMIN"


class ShiftStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    SUBMITTED = "SUBMITTED"
    MISSING_CASHOUT = "MISSING_CASHOUT"


class CashoutSubmissionStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CashoutDocumentType(StrEnum):
    CASHOUT_REPORT = "CASHOUT_REPORT"


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
