# backend/app/integrations/email/client.py

from __future__ import annotations

from typing import Protocol


class EmailDeliveryError(Exception):
    """The provider failed to deliver an email.

    Clients raise this instead of provider SDK exceptions so callers (and the
    outbox's `last_error`) see an application error naming the cause, never a
    provider's internal exception type.
    """


class EmailClient(Protocol):
    async def send(self, *, to: str, subject: str, html: str) -> None:
        """Deliver one email; raises `EmailDeliveryError` on failure."""
        ...


__all__ = ["EmailClient", "EmailDeliveryError"]
