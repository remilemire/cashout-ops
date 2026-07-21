# backend/tests/support/fixtures/db.py

"""Database fixtures: throwaway Postgres, schema, per-test truncation.

Provisioning is lazy: nothing database-related happens until a test
(transitively) requests `db_sessionmaker` or `db_session`. The autouse
`clean_tables` fixture consults `_db_state` and no-ops for tests that never
touched the database — this is what lets the unit tier run without Docker.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.db import registry


@dataclass
class ProvisionedDB:
    """Session-wide record of whether (and where) a test database exists."""

    url: str | None = None


@pytest.fixture(scope="session")
def _db_state() -> ProvisionedDB:  # pyright: ignore[reportUnusedFunction]
    # Consumed by the schema and clean_tables fixtures via name injection,
    # which pyright does not count as a reference.
    return ProvisionedDB()


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A Postgres to test against: TEST_DATABASE_URL, or a throwaway container."""
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return

    from testcontainers.postgres import (  # pyright: ignore[reportMissingTypeStubs]
        PostgresContainer,
    )

    with PostgresContainer("postgres:18", driver="psycopg") as container:
        yield str(container.get_connection_url())  # pyright: ignore[reportUnknownMemberType]


@pytest.fixture(scope="session")
def schema(postgres_url: str, _db_state: ProvisionedDB) -> Iterator[None]:
    # Schema setup/teardown uses a sync engine to stay off any test event loop.
    engine = create_engine(postgres_url)
    registry.metadata.create_all(engine)
    _db_state.url = postgres_url
    yield
    registry.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables(_db_state: ProvisionedDB) -> Iterator[None]:
    yield
    if _db_state.url is None:  # this test never provisioned the database
        return
    tables = ", ".join(table.name for table in registry.metadata.sorted_tables)
    engine = create_engine(_db_state.url)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    engine.dispose()


@pytest_asyncio.fixture
async def db_sessionmaker(
    postgres_url: str,
    schema: None,  # tables must exist before any session is handed out
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(postgres_url)
    try:
        yield async_sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with db_sessionmaker() as session:
        yield session
