# backend/app/integrations/ai/errors.py

from __future__ import annotations

from enum import StrEnum


# Provider-neutral failure modes of a structured-analysis call. The codes
# describe what happened at the AI boundary — nothing here knows what the
# content was; callers re-raise under their own domain vocabulary (see
# document_ai/errors.py).
class AIErrorCode(StrEnum):
    SERVICE_UNAVAILABLE = "service_unavailable"
    # The provider declined the content (refusal stop reason, safety block).
    CONTENT_REFUSED = "content_refused"
    # The provider answered, but not with output that validates against the
    # response model.
    INVALID_RESPONSE = "invalid_response"
    # The model hit the max-tokens limit before completing its output.
    OUTPUT_LIMIT_REACHED = "output_limit_reached"
    # The content's media type cannot be sent to the provider at all.
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"


class AIAnalysisError(Exception):
    """A structured-analysis call failed in a way callers may persist.

    Carries its own code and message: catchers translate from these alone,
    never by inspecting `__cause__`.
    """

    def __init__(self, code: AIErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


__all__ = ["AIAnalysisError", "AIErrorCode"]
