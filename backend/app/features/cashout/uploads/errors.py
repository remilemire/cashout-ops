# backend/app/features/cashout/uploads/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorKindMap

type ErrorCode = Literal[
    "UPLOAD_NOT_FOUND",
    "UPLOAD_TOO_LARGE",
    "UPLOAD_DUPLICATE",
    "UNSUPPORTED_UPLOAD_TYPE",
]

error_kind_map: ErrorKindMap[ErrorCode] = {
    "UPLOAD_NOT_FOUND": "NOT_FOUND",
    "UPLOAD_TOO_LARGE": "BAD_REQUEST",
    "UPLOAD_DUPLICATE": "CONFLICT",
    "UNSUPPORTED_UPLOAD_TYPE": "BAD_REQUEST",
}

__all__ = ["ErrorCode", "error_kind_map"]
