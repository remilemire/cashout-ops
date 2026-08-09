# backend/app/infrastructure/outbox/service.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# from .catalog import outboxMessageDefinitions


async def enqueue(db: ..., *, type: str, payload: Mapping[str, Any]) -> None:
    ...
    # AGENT: parse payload and call messages_service.insert


__all__ = ["enqueue"]
