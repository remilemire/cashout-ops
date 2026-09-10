from __future__ import annotations

from .app_error import AppError


class RateLimitedError(AppError):
    """RATE_LIMITED with the seconds until the window resets; the handlers
    emit them in context and as the Retry-After header."""

    retry_after_seconds: int

    def __init__(
        self,
        retry_after_seconds: int,
        message: str | None = None,
    ):
        super().__init__(
            "RATE_LIMITED", message, ctx={"retryAfterSeconds": retry_after_seconds}
        )
        self.retry_after_seconds = retry_after_seconds


__all__ = ["RateLimitedError"]
