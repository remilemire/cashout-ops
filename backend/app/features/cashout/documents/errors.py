# backend/app/features/cashout/documents/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorKindMap

type ErrorCode = Literal[
    "DOCUMENT_NOT_FOUND",
    "DOCUMENT_TOO_LARGE",
    "DOCUMENT_DUPLICATE",
    "UNSUPPORTED_DOCUMENT_TYPE",
]

error_kind_map: ErrorKindMap[ErrorCode] = {
    "DOCUMENT_NOT_FOUND": "NOT_FOUND",
    "DOCUMENT_TOO_LARGE": "BAD_REQUEST",
    "DOCUMENT_DUPLICATE": "CONFLICT",
    "UNSUPPORTED_DOCUMENT_TYPE": "BAD_REQUEST",
}

__all__ = ["ErrorCode", "error_kind_map"]
