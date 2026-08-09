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

# Matches ADMIN_EMAIL set in conftest; initiating a login for this email
# lazily bootstraps the admin account.
ADMIN_EMAIL = "admin@test.com"


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

    Initiates the challenge, drains the outbox to deliver the link email,
    verifies the link for the one-time code, and completes with the code;
    the client then carries session + csrf cookies.
    """
    start = await client.post("/api/auth/login", json={"email": email})
    assert start.status_code == 202, start.text

    await drain_outbox()
    link = email_client.latest_link(to=email)

    verified_link = await client.post(
        "/api/auth/login/verify-link",
        json={"challengeId": link.challenge_id, "token": link.token},
    )
    assert verified_link.status_code == 200, verified_link.text
    code = verified_link.json()["code"]

    verified_code = await client.post(
        "/api/auth/login/verify-code",
        json={"challengeId": link.challenge_id, "code": code},
    )
    assert verified_code.status_code == 200, verified_code.text
