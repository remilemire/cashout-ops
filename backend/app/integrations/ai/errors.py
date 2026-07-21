# backend/app/integrations/ai/errors.py

from __future__ import annotations

from enum import StrEnum


class AIErrorCode(StrEnum):
    PROVIDER_ERROR = "PROVIDER_ERROR"
    REFUSED = "REFUSED"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    # The model hit the max-tokens limit before completing its output.
    TRUNCATED = "TRUNCATED"
    UNSUPPORTED_CONTENT = "UNSUPPORTED_CONTENT"


class AIAnalysisError(Exception):
    """A structured-analysis call failed in a way callers may persist."""

    def __init__(self, code: AIErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


__all__ = ["AIAnalysisError", "AIErrorCode"]
