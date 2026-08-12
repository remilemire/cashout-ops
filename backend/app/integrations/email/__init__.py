# backend/app/integrations/email/__init__.py

from __future__ import annotations

from .client import EmailClient, EmailDeliveryError
from .console import ConsoleEmailClient
from .resend import ResendEmailClient

__all__ = [
    "ConsoleEmailClient",
    "EmailClient",
    "EmailDeliveryError",
    "ResendEmailClient",
]
