# backend/app/errors/app_error.py

from __future__ import annotations

from .catalog import ErrorCode


class AppError(Exception):
    """Raise with a cataloged code; the handlers format the response.

    `message` is internal-only context (it reaches logs and tracebacks, never
    the client) — the response message is always the catalog default for
    `code`.
    """

    code: ErrorCode
    message: str | None

    def __init__(self, code: ErrorCode, message: str | None = None):
        super().__init__(message or code)

        self.code = code
        self.message = message


__all__ = ["AppError"]
