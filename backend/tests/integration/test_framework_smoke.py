# backend/tests/integration/test_framework_smoke.py

"""Framework smoke tests for the integration tier.

These prove the auto-marker and the make_client factory (user seeding,
passwordless sign-in through the real API, per-test app + database).
They are not application coverage.
"""

from __future__ import annotations

from typing import cast

import pytest

from tests.support.fixtures.clients import ClientFactory


def test_integration_marker_auto_applied(request: pytest.FixtureRequest) -> None:
    # FixtureRequest.node is an un-annotated abstract property; cast to the
    # concrete item type and ignore the one unavoidably-untyped access.
    node = cast(pytest.Item, request.node)  # pyright: ignore[reportUnknownMemberType]
    assert node.get_closest_marker("integration") is not None


async def test_make_client_authenticates_fresh_user(make_client: ClientFactory) -> None:
    client = await make_client(email="fresh@test.com")

    response = await client.get("/api/users/me")

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "fresh@test.com"


async def test_make_client_supports_multiple_users(make_client: ClientFactory) -> None:
    first = await make_client()
    second = await make_client()

    first_email = (await first.get("/api/users/me")).json()["email"]
    second_email = (await second.get("/api/users/me")).json()["email"]

    assert first_email != second_email
