# backend/app/core/providers.py

from __future__ import annotations

from enum import StrEnum


class AIProvider(StrEnum):
    ANTHROPIC = "ANTHROPIC"
    OPENAI = "OPENAI"
    GEMINI = "GEMINI"


class EmailProvider(StrEnum):
    CONSOLE = "CONSOLE"
    RESEND = "RESEND"


class StorageProvider(StrEnum):
    LOCAL = "LOCAL"
    S3 = "S3"


__all__ = ["AIProvider", "EmailProvider", "StorageProvider"]
