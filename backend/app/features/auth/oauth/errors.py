from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorKindMap

# OAUTH_SIGN_IN_FAILED covers every failure reachable once the browser has
# left for the issuer (unknown/expired/replayed flow, state mismatch,
# issuer-denied callback, failed code exchange or ID-token validation, an
# identity this deployment has no account for) so the error reveals nothing
# about which check failed — least of all whether an account exists for the
# identity. OAUTH_ISSUER_NOT_ENABLED stays distinct because it is decided
# before the browser ever leaves, and states a deployment fact rather than
# anything about the identity that would have been presented.
type ErrorCode = Literal[
    "OAUTH_SIGN_IN_FAILED",
    "OAUTH_ISSUER_NOT_ENABLED",
]

error_kind_map: ErrorKindMap[ErrorCode] = {
    "OAUTH_SIGN_IN_FAILED": "UNAUTHORIZED",
    "OAUTH_ISSUER_NOT_ENABLED": "NOT_FOUND",
}

__all__ = ["ErrorCode", "error_kind_map"]
