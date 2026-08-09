# backend/app/integrations/email/console.py

from __future__ import annotations

import logging

logger = logging.getLogger("app.email")


class ConsoleEmailClient:
    """`EmailClient` that logs messages instead of sending them.

    The development/default stand-in when no `RESEND_API_KEY` is configured, so
    the app boots and the verification flow works end to end locally — the code
    lands in the server logs. Swap in `ResendEmailClient` for real delivery.
    """

    def __init__(self, *, sender: str) -> None:
        self._sender = sender

    async def send(self, *, to: str, subject: str, html: str) -> None:
        logger.info(
            "Email not sent (console client): from=%s to=%s subject=%r\n%s",
            self._sender,
            to,
            subject,
            html,
        )


__all__ = ["ConsoleEmailClient"]
