from __future__ import annotations

from pydantic import JsonValue

from .catalog import ErrorCode


class AppError(Exception):
    """A public code and JSON context; the frontend owns the wording.

    `message` is internal diagnostic detail, never sent to clients. Only put
    deliberately public values in `ctx`; it is serialized as supplied.
    """

    code: ErrorCode
    message: str | None
    ctx: dict[str, JsonValue]

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        ctx: dict[str, JsonValue] | None = None,
    ):
        super().__init__(message or code)

        self.code = code
        self.message = message
        self.ctx = dict(ctx) if ctx is not None else {}


__all__ = ["AppError"]
