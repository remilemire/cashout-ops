# backend/app/integrations/ai/errors.py

from __future__ import annotations

from enum import StrEnum


class AIErrorCode(StrEnum):
    SERVICE_UNAVAILABLE = "service_unavailable"
    DOCUMENT_REJECTED = "document_rejected"
    UNREADABLE_DOCUMENT = "unreadable_document"
    # The model hit the max-tokens limit before completing its output.
    OUTPUT_LIMIT_REACHED = "output_limit_reached"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"


class AIAnalysisError(Exception):
    """A structured-analysis call failed in a way callers may persist."""

    def __init__(self, code: AIErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


__all__ = ["AIAnalysisError", "AIErrorCode"]
