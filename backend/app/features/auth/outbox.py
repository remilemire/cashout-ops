"""Aggregated outbox surface for the auth feature.

Message definitions and handlers live with their owning sub-features; this
module only collects and re-exports them for the outbox catalog and the
composition root.
"""

from __future__ import annotations

from app.core.outbox import OutboxMessageDefinitionList

from .email_challenges.outbox import (
    OutboxMessageType as EmailChallengeOutboxMessageType,
)
from .email_challenges.outbox import SendLoginCodeEmailOutboxHandler
from .email_challenges.outbox import (
    outbox_message_definitions as email_challenge_outbox_message_definitions,
)

type OutboxMessageType = EmailChallengeOutboxMessageType

outbox_message_definitions: OutboxMessageDefinitionList[OutboxMessageType] = [
    *email_challenge_outbox_message_definitions,
]

__all__ = [
    "OutboxMessageType",
    "SendLoginCodeEmailOutboxHandler",
    "outbox_message_definitions",
]
