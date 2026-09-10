from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorKindMap

# ONE code covers every failure mode (unknown/expired challenge, code not
# yet emailed, wrong code, code attempts exceeded, already consumed, deleted
# user) so the error shape cannot be used for account enumeration.
type ErrorCode = Literal["EMAIL_CHALLENGE_INVALID"]

error_kind_map: ErrorKindMap[ErrorCode] = {
    "EMAIL_CHALLENGE_INVALID": "UNAUTHORIZED",
}

__all__ = ["ErrorCode", "error_kind_map"]
