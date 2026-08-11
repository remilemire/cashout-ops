# backend/app/features/auth/outbox.py

"""Aggregated outbox surface for the auth feature.

Message definitions and handlers live with their owning sub-features; this
module only collects and re-exports them for the outbox catalog and the
composition root.
"""

from __future__ import annotations

from app.infrastructure.outbox.contracts import OutboxMessageDefinition

from .email_challenges.outbox import (
    SendLoginLinkEmailOutboxHandler,
    send_login_link_email_message,
)

auth_outbox_message_definitions: list[OutboxMessageDefinition] = [
    send_login_link_email_message,
]

__all__ = [
    "SendLoginLinkEmailOutboxHandler",
    "auth_outbox_message_definitions",
    "send_login_link_email_message",
]
