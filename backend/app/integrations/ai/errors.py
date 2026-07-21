# backend/app/integrations/ai/errors.py

from __future__ import annotations

from enum import StrEnum


class AIErrorCode(StrEnum):
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED"
    UNREADABLE_DOCUMENT = "UNREADABLE_DOCUMENT"
    # The model hit the max-tokens limit before completing its output.
    OUTPUT_LIMIT_REACHED = "OUTPUT_LIMIT_REACHED"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"


class AIAnalysisError(Exception):
    """A structured-analysis call failed in a way callers may persist."""

    def __init__(self, code: AIErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


__all__ = ["AIAnalysisError", "AIErrorCode"]
