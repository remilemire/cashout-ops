from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.providers import EmailProvider

from .client import EmailClient
from .console import ConsoleEmailClient
from .resend import ResendEmailClient


@asynccontextmanager
async def email_lifespan() -> AsyncGenerator[EmailClient]:
    """Build the configured email client; no teardown is required."""
    yield _build_email_client()


def _build_email_client() -> EmailClient:
    """Select the configured email client.

    Settings already rejects RESEND without its API key, so the guard below
    narrows that optional field for the type checker rather than enforcing
    the requirement itself.
    """
    if settings.email.PROVIDER is EmailProvider.RESEND:
        if not settings.email.RESEND_API_KEY:
            raise RuntimeError(
                "RESEND_API_KEY is required when EMAIL_PROVIDER is RESEND."
            )
        return ResendEmailClient(
            api_key=settings.email.RESEND_API_KEY, sender=settings.email.FROM
        )
    return ConsoleEmailClient(sender=settings.email.FROM)
