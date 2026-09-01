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

    def latest_code(self, *, to: str | None = None) -> str:
        """The 6-digit sign-in code from the most recent matching email.

        The outbox handler emails the code, which is the only channel a test
        can learn it from (Redis stores only its hash). The TTL rendered in
        the body is 2 digits, so a 6-digit match is unambiguous.
        """
        for email in reversed(self.sent):
            if to is not None and email.to != to:
                continue
            code = re.search(r"\b\d{6}\b", email.html)
            if code is not None:
                return code.group(0)
        raise AssertionError(f"no sign-in code emailed (to={to!r})")


__all__ = ["FakeEmailClient", "SentEmail"]
