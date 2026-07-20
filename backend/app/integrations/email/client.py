# backend/app/integrations/email/client.py

from __future__ import annotations

from typing import Protocol


class EmailClient(Protocol):
    async def send(self, *, to: str, subject: str, html: str) -> None: ...


__all__ = ["EmailClient"]
