# backend/app/integrations/email/resend.py

from __future__ import annotations

import asyncio

import resend

from .client import EmailClient, EmailDeliveryError


class ResendEmailClient(EmailClient):
    """`EmailClient` backed by Resend (https://resend.com).

    The Resend SDK is synchronous and keeps its API key in a module global, so
    the key is set once here and each send is offloaded to a worker thread to
    keep the event loop free.
    """

    def __init__(self, *, api_key: str, sender: str) -> None:
        resend.api_key = api_key
        self._sender = sender

    async def send(self, *, to: str, subject: str, html: str) -> None:
        params: resend.Emails.SendParams = {
            "from": self._sender,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        try:
            await asyncio.to_thread(resend.Emails.send, params)
        except Exception as error:
            raise EmailDeliveryError(f"Resend send to {to} failed: {error}") from error


__all__ = ["ResendEmailClient"]
