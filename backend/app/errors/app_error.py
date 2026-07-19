# backend/app/errors/app_error.py

from __future__ import annotations

from typing import TYPE_CHECKING

# Runtime import would recurse: codes.py imports the feature error modules,
# which import app.errors.contracts and thereby initialize this package.
if TYPE_CHECKING:
    from .codes import ErrorCode


class AppError(Exception):
    """Raise with a cataloged code; the handlers format the response.

    `message` overrides the catalog default for this occurrence; `cause` keeps
    the originating exception for logging without leaking it to the client.
    """

    code: ErrorCode
    message: str | None
    cause: Exception | None

    def __init__(
        self,
        code: ErrorCode,
        *,
        message: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message or code)

        self.code = code
        self.message = message
        self.cause = cause


__all__ = ["AppError"]
