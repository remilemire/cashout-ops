# backend/app/features/cashout/analyses/messages.py

"""User-facing messages for FAILED document analyses.

Keyed by the persisted `error_code` (the AIErrorCode raised by the AI layer).
Raw provider messages are never surfaced on the analysis — they can leak
internal/provider detail — so every failure maps its code to one of these.
Log the raw text instead.
"""

from __future__ import annotations

from app.integrations.ai import AIErrorCode

_ANALYSIS_ERROR_MESSAGES: dict[str, str] = {
    AIErrorCode.SERVICE_UNAVAILABLE.value: (
        "The document service is temporarily unavailable. Please try again."
    ),
    AIErrorCode.DOCUMENT_REJECTED.value: (
        "This document could not be processed. Please check it and try again."
    ),
    AIErrorCode.UNREADABLE_DOCUMENT.value: (
        "The document could not be read. Please retry or re-upload a clearer copy."
    ),
    AIErrorCode.OUTPUT_LIMIT_REACHED.value: (
        "This document was too large for the AI to read in full. Try cropping "
        "the image to just the report."
    ),
    AIErrorCode.UNSUPPORTED_FILE_TYPE.value: ("This file type isn't supported."),
}

_DEFAULT_ANALYSIS_ERROR_MESSAGE = "Analysis failed unexpectedly. Please try again."


def analysis_error_message(code: str | None = None) -> str:
    """User-facing message for a persisted analysis error_code.

    `None` (an unexpected job crash — no AI error code) and unmapped codes get
    the generic default.
    """
    return _ANALYSIS_ERROR_MESSAGES.get(code or "", _DEFAULT_ANALYSIS_ERROR_MESSAGE)


__all__ = ["analysis_error_message"]
