from __future__ import annotations

import logging

logger = logging.getLogger("app.email")


class ConsoleEmailClient:
    """Log email content for local development when EMAIL_PROVIDER=console.

    Codes appear in the server logs. Selection is explicit: missing Resend
    credentials do not cause an automatic fallback to this client.
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
