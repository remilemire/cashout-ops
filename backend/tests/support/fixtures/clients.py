# backend/tests/support/fixtures/clients.py

"""HTTP clients over the per-test app, including the make_client factory."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Protocol
from uuid import uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..api import ADMIN_EMAIL, DEFAULT_PASSWORD, register
from ..factories import create_invitation, verify_user


class ClientFactory(Protocol):
    async def __call__(
        self,
        *,
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
        full_name: str = "Test User",
        admin: bool = False,
        verified: bool = True,
    ) -> AsyncClient: ...


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An anonymous client (no session cookies)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def make_client(
    app: FastAPI, db_sessionmaker: async_sessionmaker[AsyncSession]
) -> AsyncIterator[ClientFactory]:
    """Factory for authenticated clients; call repeatedly for multi-user tests.

    Registers through the real API so the returned client carries session +
    csrf cookies, seeding the required invitation first. `admin=True` registers
    ADMIN_EMAIL instead, which auto-promotes and needs no invitation. Omitting
    `email` picks a unique address. All clients close at fixture teardown.
    """
    async with contextlib.AsyncExitStack() as stack:

        async def _make(
            *,
            email: str | None = None,
            password: str = DEFAULT_PASSWORD,
            full_name: str = "Test User",
            admin: bool = False,
            verified: bool = True,
        ) -> AsyncClient:
            resolved = (
                ADMIN_EMAIL if admin else (email or f"user-{uuid4().hex[:8]}@test.com")
            )
            if not admin:
                async with db_sessionmaker() as db:
                    await create_invitation(db, email=resolved)
            http_client = await stack.enter_async_context(
                AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
            )
            await register(
                http_client, email=resolved, full_name=full_name, password=password
            )
            if verified:
                async with db_sessionmaker() as db:
                    await verify_user(db, email=resolved)
            return http_client

        yield _make


@pytest_asyncio.fixture
async def unverified_client(make_client: ClientFactory) -> AsyncClient:
    """A registered cashier that has NOT verified its email (for the gate flow)."""
    return await make_client(email="cashier@test.com", verified=False)


@pytest_asyncio.fixture
async def cashier_client(make_client: ClientFactory) -> AsyncClient:
    return await make_client(email="cashier@test.com")


@pytest_asyncio.fixture
async def admin_client(make_client: ClientFactory) -> AsyncClient:
    return await make_client(admin=True, full_name="Admin User")
