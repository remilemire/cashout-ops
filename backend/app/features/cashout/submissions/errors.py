from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorKindMap

type ErrorCode = Literal[
    "SUBMISSION_NOT_FOUND",
    "SUBMISSION_COMPLETED",
    "SUBMISSION_NOT_COMPLETED",
    "SUBMISSION_EMPTY",
    "SUBMISSION_UNVERIFIED",
    "SUBMISSION_HAS_DATA",
    "SUBMISSION_DUPLICATE_DAY",
]

error_kind_map: ErrorKindMap[ErrorCode] = {
    "SUBMISSION_NOT_FOUND": "NOT_FOUND",
    "SUBMISSION_COMPLETED": "CONFLICT",
    "SUBMISSION_NOT_COMPLETED": "CONFLICT",
    "SUBMISSION_EMPTY": "CONFLICT",
    "SUBMISSION_UNVERIFIED": "CONFLICT",
    "SUBMISSION_HAS_DATA": "CONFLICT",
    "SUBMISSION_DUPLICATE_DAY": "CONFLICT",
}

__all__ = ["ErrorCode", "error_kind_map"]
