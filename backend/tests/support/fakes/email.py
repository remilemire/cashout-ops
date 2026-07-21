# backend/tests/support/fakes/email.py

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SentEmail:
    to: str
    subject: str
    html: str


class FakeEmailClient:
    """`EmailClient` that records sent messages instead of delivering them."""

    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    async def send(self, *, to: str, subject: str, html: str) -> None:
        self.sent.append(SentEmail(to=to, subject=subject, html=html))

    def latest_code(self, *, to: str | None = None) -> str:
        """The verification code from the most recent matching email.

        The service emails a `_CODE_DIGITS`-digit numeric code, which is the
        only channel a test can learn it from (the DB stores only the hash).
        """
        for email in reversed(self.sent):
            if to is not None and email.to != to:
                continue
            match = re.search(r"\d{6}", email.html)
            if match is not None:
                return match.group()
        raise AssertionError(f"no verification code emailed (to={to!r})")
