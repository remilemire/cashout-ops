# backend/app/features/auth/outbox.py

"""Outbox message definitions and handlers for the auth feature.

Register and resend enqueue `auth.send_verification_email` in their request
transaction; the handler issues the code and sends the email at dispatch.
Login initiation enqueues `auth.send_login_link_email` the same way; the
handler mints the link token and emails the magic sign-in link.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel

from app.infrastructure.outbox.contracts import OutboxMessageDefinition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.infrastructure.redis import Redis
    from app.integrations.email import EmailClient

logger = logging.getLogger(__name__)


class SendVerificationEmail(BaseModel):
    user_id: UUID


send_verification_email_message = OutboxMessageDefinition(
    "auth.send_verification_email", SendVerificationEmail
)

# Verification emails give up quickly (about a minute at the default backoff)
# instead of retrying for an hour: the user is sitting on the verify screen
# and can always hit resend.
SEND_VERIFICATION_EMAIL_MAX_ATTEMPTS = 5


class SendLoginLinkEmail(BaseModel):
    challenge_id: str
    user_id: UUID


send_login_link_email_message = OutboxMessageDefinition(
    "auth.send_login_link_email", SendLoginLinkEmail
)

# Sign-in link emails give up quickly (about a minute at the default backoff)
# instead of retrying for an hour: the user is sitting on the login screen
# and can always start a fresh challenge.
SEND_LOGIN_LINK_EMAIL_MAX_ATTEMPTS = 5

auth_outbox_message_definitions: list[OutboxMessageDefinition] = [
    send_verification_email_message,
    send_login_link_email_message,
]


class SendVerificationEmailOutboxHandler:
    """Issues a fresh verification code and emails it to the user.

    The payload carries only the user id — the code is generated inside
    `send_new_code` at delivery time, so no secret ever lands in the
    outbox table.
    """

    message = send_verification_email_message

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
        email_client: EmailClient,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._redis = redis
        self._email_client = email_client

    async def handle(self, payload: SendVerificationEmail) -> None:
        # Imported at call time: the outbox catalog imports this module, and
        # the email-verification service will import the outbox to enqueue —
        # a module-level service import would close that cycle.
        from .email_verification.service import send_new_code

        await send_new_code(
            self._sessionmaker,
            self._redis,
            email_client=self._email_client,
            user_id=payload.user_id,
        )

    async def on_dead_letter(self, payload: SendVerificationEmail) -> None:
        # The user can always request a resend, so losing the message only
        # needs to be visible, not repaired.
        logger.error(
            "Verification email outbox message dead-lettered for user %s",
            payload.user_id,
        )


class SendLoginLinkEmailOutboxHandler:
    """Mints the link token and emails the magic sign-in link.

    The payload carries only ids — the token is generated inside
    `send_login_link_email` at delivery time, so no secret ever lands in the
    outbox table.
    """

    message = send_login_link_email_message

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
        # Imported at call time: the outbox catalog imports this module, and
        # the login-challenges service imports the outbox to enqueue — a
        # module-level service import would close that cycle.
        from .login_challenges.service import send_login_link_email

        await send_login_link_email(
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
    "SEND_VERIFICATION_EMAIL_MAX_ATTEMPTS",
    "SendLoginLinkEmail",
    "SendLoginLinkEmailOutboxHandler",
    "SendVerificationEmail",
    "SendVerificationEmailOutboxHandler",
    "auth_outbox_message_definitions",
    "send_login_link_email_message",
    "send_verification_email_message",
]
