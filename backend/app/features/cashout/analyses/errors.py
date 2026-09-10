from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorKindMap

type ErrorCode = Literal[
    "ANALYSIS_NOT_FOUND",
    "ANALYSIS_VERIFIED",
    "ANALYSIS_NOT_VERIFIED",
    "EXTRACTION_IN_PROGRESS",
    "EXTRACTION_FAILED",
    "CROP_NOT_FOUND",
]

error_kind_map: ErrorKindMap[ErrorCode] = {
    "ANALYSIS_NOT_FOUND": "NOT_FOUND",
    "ANALYSIS_VERIFIED": "CONFLICT",
    "ANALYSIS_NOT_VERIFIED": "CONFLICT",
    "EXTRACTION_IN_PROGRESS": "CONFLICT",
    "EXTRACTION_FAILED": "CONFLICT",
    # The analysis exists but has no crop to serve: it read the upload whole,
    # or the stored crop is gone.
    "CROP_NOT_FOUND": "NOT_FOUND",
}

__all__ = ["ErrorCode", "error_kind_map"]
