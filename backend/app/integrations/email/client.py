from __future__ import annotations

from typing import Protocol


class EmailClient(Protocol):
    async def send(self, *, to: str, subject: str, html: str) -> None:
        """Deliver one email; raises `EmailDeliveryError` on failure."""
        ...


__all__ = ["EmailClient"]
