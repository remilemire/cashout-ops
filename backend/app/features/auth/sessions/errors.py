# backend/app/features/auth/sessions/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorKindMap

type ErrorCode = Literal["INVALID_SESSION"]

error_kind_map: ErrorKindMap[ErrorCode] = {
    "INVALID_SESSION": "UNAUTHORIZED",
}

__all__ = ["ErrorCode", "error_kind_map"]
