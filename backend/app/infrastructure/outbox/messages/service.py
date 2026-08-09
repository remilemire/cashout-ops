# backend/app/infrastructure/outbox/messages/service.py

from __future__ import annotations

from pydantic import BaseModel

# AGENT: TODO


async def insert_outbox_message(db: ..., *, type: str, payload: BaseModel) -> ...: ...


__all__ = ["insert_outbox_message"]
