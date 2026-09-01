# backend/tests/support/api.py

"""Drivers for the authentication API and CSRF handling in tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from httpx import AsyncClient

if TYPE_CHECKING:
    # Type-only: importing the plugin module at runtime would beat pytest's
    # own (assertion-rewriting) import of it and trigger a rewrite warning.
    from .fakes import FakeEmailClient
    from .fixtures.outbox import OutboxDrain

# Matches BOOTSTRAP_OWNER_EMAIL set in conftest; completing a login for this
# email lazily bootstraps the owner account (initiating one does not).
OWNER_EMAIL = "owner@test.com"


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    """The x-csrf-token header matching the readable csrf cookie, for unsafe methods."""
    token = client.cookies.get("csrf_token")
    assert token is not None, "no csrf cookie set; log in first"
    return {"x-csrf-token": token}


async def login(
    client: AsyncClient,
    *,
    email: str = "cashier@test.com",
    drain_outbox: OutboxDrain,
    email_client: FakeEmailClient,
) -> None:
    """Sign in through the passwordless challenge flow.

    Initiates the challenge, drains the outbox to deliver the code email,
    and completes with the emailed code; the client then carries
    session + csrf cookies.
    """
    start = await client.post("/api/auth/email-challenges", json={"email": email})
    assert start.status_code == 202, start.text
    challenge_id = start.json()["challengeId"]

    await drain_outbox()
    code = email_client.latest_code(to=email)

    verified_code = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": challenge_id, "code": code},
    )
    assert verified_code.status_code == 200, verified_code.text


__all__ = ["OWNER_EMAIL", "csrf_headers", "login"]
