# backend/app/features/cashout/analyses/messages.py

"""User-facing messages for FAILED document analyses.

Keyed by the persisted `error_code` — the DocumentAIErrorCode raised by the
document-AI layer (its own unclassifiable-document failure, or an AI-layer
failure re-raised under document vocabulary). Raw provider messages are never
surfaced on the analysis — they can leak internal/provider detail — so every
failure maps its code to one of these. Log the raw text instead.
"""

from __future__ import annotations

from app.document_ai import DocumentAIErrorCode

_ANALYSIS_ERROR_MESSAGES: dict[str, str] = {
    DocumentAIErrorCode.UNCLASSIFIABLE_DOCUMENT.value: (
        "This doesn't look like a cashout report. Retry, replace it with a "
        "clearer copy, or enter the details manually."
    ),
    DocumentAIErrorCode.SERVICE_UNAVAILABLE.value: (
        "The document service is temporarily unavailable. Please try again."
    ),
    DocumentAIErrorCode.DOCUMENT_REJECTED.value: (
        "This document could not be processed. Please check it and try again."
    ),
    DocumentAIErrorCode.UNREADABLE_DOCUMENT.value: (
        "The document could not be read. Please retry or re-upload a clearer copy."
    ),
    DocumentAIErrorCode.OUTPUT_LIMIT_REACHED.value: (
        "This document was too large for the AI to read in full. Try cropping "
        "the image to just the report."
    ),
    DocumentAIErrorCode.UNSUPPORTED_FILE_TYPE.value: (
        "This file type isn't supported."
    ),
}

_DEFAULT_ANALYSIS_ERROR_MESSAGE = "Analysis failed unexpectedly. Please try again."


def analysis_error_message(code: str | None = None) -> str:
    """User-facing message for a persisted analysis error_code.

    `None` (an unexpected job crash — no document-AI error code) and unmapped
    codes get the generic default.
    """
    return _ANALYSIS_ERROR_MESSAGES.get(code or "", _DEFAULT_ANALYSIS_ERROR_MESSAGE)


__all__ = ["analysis_error_message"]
