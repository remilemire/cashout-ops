# backend/app/features/cashout/submissions/types.py

from __future__ import annotations

from enum import StrEnum


# PROCESSING covers the whole open phase (uploading, extracting, verifying);
# completion reconciles the verified analyses and closes the submission.
class CashoutSubmissionStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"


__all__ = ["CashoutSubmissionStatus"]
