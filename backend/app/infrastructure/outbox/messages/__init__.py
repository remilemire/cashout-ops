# backend/app/infrastructure/outbox/messages/__init__.py

from __future__ import annotations

from .model import OutboxMessage
from .service import insert_outbox_message

__all__ = ["insert_outbox_message", "OutboxMessage"]
