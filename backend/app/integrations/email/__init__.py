from __future__ import annotations

from .client import EmailClient
from .console import ConsoleEmailClient
from .errors import EmailDeliveryError
from .resend import ResendEmailClient

__all__ = [
    "ConsoleEmailClient",
    "EmailClient",
    "EmailDeliveryError",
    "ResendEmailClient",
]
