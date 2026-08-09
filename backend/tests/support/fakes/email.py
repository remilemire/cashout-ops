# backend/tests/support/fakes/email.py

from __future__ import annotations

import re
from dataclasses import dataclass

from app.integrations.email import EmailClient


@dataclass(frozen=True)
class SentEmail:
    to: str
    subject: str
    html: str


@dataclass(frozen=True)
class LoginLink:
    challenge_id: str
    token: str


class FakeEmailClient(EmailClient):
    """`EmailClient` that records sent messages instead of delivering them.

    Set `fail_with` to make subsequent sends raise instead of recording, for
    testing delivery-failure paths (e.g. outbox retries).
    """

    def __init__(self) -> None:
        self.sent: list[SentEmail] = []
        self.fail_with: Exception | None = None

    async def send(self, *, to: str, subject: str, html: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(SentEmail(to=to, subject=subject, html=html))

    def latest_link(self, *, to: str | None = None) -> LoginLink:
        """The sign-in link parameters from the most recent matching email.

        The service emails a magic link carrying the challenge id and token,
        which is the only channel a test can learn the token from (Redis
        stores only its hash).
        """
        for email in reversed(self.sent):
            if to is not None and email.to != to:
                continue
            challenge = re.search(r"challenge=([0-9a-f-]{36})", email.html)
            token = re.search(r"token=([A-Za-z0-9_-]+)", email.html)
            if challenge is not None and token is not None:
                return LoginLink(challenge_id=challenge.group(1), token=token.group(1))
        raise AssertionError(f"no sign-in link emailed (to={to!r})")
