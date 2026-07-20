# backend/app/integrations/email/__init__.py

from __future__ import annotations

from .client import EmailClient
from .console import ConsoleEmailClient
from .provider import EmailProvider
from .resend import ResendEmailClient

__all__ = [
    "ConsoleEmailClient",
    "EmailClient",
    "EmailProvider",
    "ResendEmailClient",
]
