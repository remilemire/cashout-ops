# backend/app/features/auth/email_challenges/outbox.py

"""Outbox message definition and handler for email challenges.

Initiation enqueues `auth.send_login_code_email` in its request
transaction; at dispatch the handler mints the 6-digit code and emails it.
"""

from __future__ import annotations

import logging
import secrets
from importlib.resources import files
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from app.core.config import settings
from app.core.outbox import OutboxMessageDefinition, OutboxMessageDefinitionList
from app.security.crypto import hash_secret_token

from . import store

if TYPE_CHECKING:
    from app.infrastructure.redis import Redis
    from app.integrations.email import EmailClient

logger = logging.getLogger(__name__)

_SUBJECT = "Your Whiskey District sign-in code"
# The email body template ships with this feature; render it with the code.
_TEMPLATE = (
    files("app.features.auth.email_challenges")
    .joinpath("templates", "login_code.html")
    .read_text(encoding="utf-8")
)

# Six numeric digits (leading zeros allowed).
CODE_DIGITS = 6


type OutboxMessageType = Literal["auth.send_login_code_email"]


class SendLoginCodeEmail(BaseModel):
    challenge_id: str


_send_login_code_email_message: OutboxMessageDefinition[
    OutboxMessageType, SendLoginCodeEmail
] = OutboxMessageDefinition("auth.send_login_code_email", SendLoginCodeEmail)

outbox_message_definitions: OutboxMessageDefinitionList[OutboxMessageType] = [
    _send_login_code_email_message
]

# Sign-in code emails give up quickly (about a minute at the default backoff)
# instead of retrying for an hour: the user is sitting on the login screen
# and can always start a fresh challenge.
SEND_LOGIN_CODE_EMAIL_MAX_ATTEMPTS = 5


def _generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def _render_html(*, code: str, ttl_minutes: int) -> str:
    return _TEMPLATE.replace("{{code}}", code).replace(
        "{{ttl_minutes}}", str(ttl_minutes)
    )


async def _send_login_code_email(
    redis: Redis,
    *,
    email_client: EmailClient,
    challenge_id: str,
) -> None:
    """Mint the 6-digit code and email it.

    Runs once the initiating request has committed. The recipient is the
    challenge's own address, so delivery needs no database access — and no
    email address is persisted in the outbox payload. The code hash is
    written to the challenge BEFORE the send: a retry regenerates and
    overwrites it, so the most recently emailed code is always the live one,
    and a crash between the write and the send never leaves an
    emailed-but-unstored code.
    """
    ttl_minutes = settings.auth.CHALLENGE_TTL_MINUTES

    challenge = await store.find(redis, challenge_id=challenge_id)
    if challenge is None:
        # Expired (or consumed) before delivery — stale work, not an error.
        logger.info("Login code skipped: challenge %s no longer exists", challenge_id)
        return

    code = _generate_code()
    challenge.code_hash = hash_secret_token(code)
    if not await store.update(redis, challenge_id=challenge_id, challenge=challenge):
        return  # expired mid-flight

    await email_client.send(
        to=challenge.email,
        subject=_SUBJECT,
        html=_render_html(code=code, ttl_minutes=ttl_minutes),
    )


class SendLoginCodeEmailOutboxHandler:
    """Mints the 6-digit code and emails it.

    The payload carries only the challenge id — the code is generated inside
    `_send_login_code_email` at delivery time, so no secret ever lands in the
    outbox table, and the recipient address stays in the expiring Redis
    challenge rather than in a permanently retained outbox row.
    """

    message = _send_login_code_email_message

    def __init__(self, redis: Redis, email_client: EmailClient) -> None:
        self._redis = redis
        self._email_client = email_client

    async def handle(self, payload: SendLoginCodeEmail) -> None:
        await _send_login_code_email(
            self._redis,
            email_client=self._email_client,
            challenge_id=payload.challenge_id,
        )

    async def on_dead_letter(self, payload: SendLoginCodeEmail) -> None:
        # The user can always start a fresh login, so losing the message only
        # needs to be visible, not repaired.
        logger.error(
            "Login code outbox message dead-lettered for challenge %s",
            payload.challenge_id,
        )


__all__ = [
    "SEND_LOGIN_CODE_EMAIL_MAX_ATTEMPTS",
    "OutboxMessageType",
    "SendLoginCodeEmailOutboxHandler",
    "outbox_message_definitions",
]
