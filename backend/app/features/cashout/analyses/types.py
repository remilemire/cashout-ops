from __future__ import annotations

from enum import StrEnum


# Extraction: EXTRACTING (queued or running) → NEEDS_VERIFICATION or FAILED.
# Verification: NEEDS_VERIFICATION → VERIFIED; unverify reverses this step.
# Retry returns a settled, unverified analysis to EXTRACTING; manual entry
# can replace it with VERIFIED. Unexpected failures may have no error_code.
class DocumentAnalysisStatus(StrEnum):
    EXTRACTING = "extracting"
    NEEDS_VERIFICATION = "needs_verification"
    VERIFIED = "verified"
    FAILED = "failed"


__all__ = ["DocumentAnalysisStatus"]
