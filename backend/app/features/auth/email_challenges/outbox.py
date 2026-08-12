# backend/app/features/auth/email_challenges/outbox.py

"""Outbox message definition and handler for email challenges.

Initiation enqueues `auth.send_login_link_email` in its request
transaction; at dispatch the handler mints the link token and emails the
magic sign-in link.
"""

from __future__ import annotations

import logging
from importlib.resources import files
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import BaseModel

from app.core.config import settings
from app.core.outbox import OutboxMessageDefinition, OutboxMessageDefinitionList
from app.features.users import service as users_service
from app.security.crypto import generate_secret_token, hash_secret_token

from . import store

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.infrastructure.redis import Redis
    from app.integrations.email import EmailClient

logger = logging.getLogger(__name__)

_SUBJECT = "Your Whiskey District sign-in link"
# The email body template ships with this feature; render it with the link.
_TEMPLATE = (
    files("app.features.auth.email_challenges")
    .joinpath("templates", "login_link.html")
    .read_text(encoding="utf-8")
)


type OutboxMessageType = Literal["auth.send_login_link_email"]


class SendLoginLinkEmail(BaseModel):
    challenge_id: str
    user_id: UUID


_send_login_link_email_message: OutboxMessageDefinition[
    OutboxMessageType, SendLoginLinkEmail
] = OutboxMessageDefinition("auth.send_login_link_email", SendLoginLinkEmail)

outbox_message_definitions: OutboxMessageDefinitionList[OutboxMessageType] = [
    _send_login_link_email_message
]

# Sign-in link emails give up quickly (about a minute at the default backoff)
# instead of retrying for an hour: the user is sitting on the login screen
# and can always start a fresh challenge.
SEND_LOGIN_LINK_EMAIL_MAX_ATTEMPTS = 5


def _render_html(*, link: str, ttl_minutes: int) -> str:
    return _TEMPLATE.replace("{{link}}", link).replace(
        "{{ttl_minutes}}", str(ttl_minutes)
    )


async def _send_login_link_email(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    email_client: EmailClient,
    challenge_id: str,
    user_id: UUID,
) -> None:
    """Mint the link token and email the magic sign-in link.

    Runs once the initiating request has committed, so it owns its session
    and transaction. The token hash is written to the challenge BEFORE the
    send: a retry regenerates and overwrites it, so the most recently
    emailed link is always the live one, and a crash between the write and
    the send never leaves an emailed-but-unstored token.
    """
    ttl_minutes = settings.auth.CHALLENGE_TTL_MINUTES

    async with sessionmaker() as db:
        user = await users_service.find_by_id(db, user_id=user_id)
        if user is None:
            logger.info("Login link skipped: user %s no longer exists", user_id)
            return
        recipient = user.email

    challenge = await store.find(redis, challenge_id=challenge_id)
    if challenge is None:
        # Expired (or consumed) before delivery — stale work, not an error.
        logger.info("Login link skipped: challenge %s no longer exists", challenge_id)
        return

    token = generate_secret_token()
    challenge.token_hash = hash_secret_token(token)
    if not await store.update(redis, challenge_id=challenge_id, challenge=challenge):
        return  # expired mid-flight

    base_url = settings.app.BASE_URL.rstrip("/")
    link = f"{base_url}/login/link?challenge={challenge_id}&token={token}"

    await email_client.send(
        to=recipient,
        subject=_SUBJECT,
        html=_render_html(link=link, ttl_minutes=ttl_minutes),
    )


class SendLoginLinkEmailOutboxHandler:
    """Mints the link token and emails the magic sign-in link.

    The payload carries only ids — the token is generated inside
    `_send_login_link_email` at delivery time, so no secret ever lands in
    the outbox table.
    """

    message = _send_login_link_email_message

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
        email_client: EmailClient,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._redis = redis
        self._email_client = email_client

    async def handle(self, payload: SendLoginLinkEmail) -> None:
        await _send_login_link_email(
            self._sessionmaker,
            self._redis,
            email_client=self._email_client,
            challenge_id=payload.challenge_id,
            user_id=payload.user_id,
        )

    async def on_dead_letter(self, payload: SendLoginLinkEmail) -> None:
        # The user can always start a fresh login, so losing the message only
        # needs to be visible, not repaired.
        logger.error(
            "Login link outbox message dead-lettered for challenge %s (user %s)",
            payload.challenge_id,
            payload.user_id,
        )


__all__ = [
    "SEND_LOGIN_LINK_EMAIL_MAX_ATTEMPTS",
    "OutboxMessageType",
    "SendLoginLinkEmailOutboxHandler",
    "outbox_message_definitions",
]
