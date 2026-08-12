# backend/app/core/email.py

from __future__ import annotations

from enum import StrEnum


class EmailProvider(StrEnum):
    CONSOLE = "CONSOLE"
    RESEND = "RESEND"


__all__ = ["EmailProvider"]
