# backend/tests/conftest.py

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# The throwaway Postgres is cleaned up by the fixture's `with` block, so disable
# testcontainers' Ryuk reaper (it needs a separate image that may be unavailable).
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# Required settings must exist before anything imports app.core.config. Set them
# here so the suite runs without a .env (e.g. in CI); os.environ wins over .env.
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused/unused")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")

from app.core.db import registry  # noqa: E402
from app.dependencies import (  # noqa: E402
    get_cashout_document_processor,
    get_db,
    get_db_sessionmaker,
    get_document_storage,
)
from app.documents import DocumentAIClient  # noqa: E402
from app.features.cashout.extraction import CashoutDocumentProcessor  # noqa: E402

from .fakes import FakeAIClient, FakeDocumentStorage  # noqa: E402

# ================================
# ----------- Database -----------
# ================================


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
def schema(postgres_url: str) -> Iterator[None]:
    # Schema setup/teardown uses a sync engine to stay off any test event loop.
    engine = create_engine(postgres_url)
    registry.metadata.create_all(engine)
    yield
    registry.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables(schema: None, postgres_url: str) -> Iterator[None]:
    yield
    tables = ", ".join(table.name for table in registry.metadata.sorted_tables)
    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    engine.dispose()


@pytest_asyncio.fixture
async def db_sessionmaker(
    postgres_url: str,
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


# ================================
# ---------- Integrations --------
# ================================


@pytest.fixture
def storage() -> FakeDocumentStorage:
    return FakeDocumentStorage()


@pytest.fixture
def ai_client() -> FakeAIClient:
    return FakeAIClient()


@pytest.fixture
def processor(
    ai_client: FakeAIClient, storage: FakeDocumentStorage
) -> CashoutDocumentProcessor:
    # Real processor + DocumentAIClient over the fake provider and storage.
    return CashoutDocumentProcessor(DocumentAIClient(ai_client, storage))


# ================================
# ------------- App --------------
# ================================


@pytest_asyncio.fixture
async def app(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    processor: CashoutDocumentProcessor,
    storage: FakeDocumentStorage,
) -> AsyncIterator[FastAPI]:
    from app.main import app as fastapi_app

    async def _get_db() -> AsyncIterator[AsyncSession]:
        async with db_sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    fastapi_app.dependency_overrides[get_db] = _get_db
    # Background tasks (document extraction) build their own session from this.
    fastapi_app.dependency_overrides[get_db_sessionmaker] = lambda: db_sessionmaker
    fastapi_app.dependency_overrides[get_cashout_document_processor] = lambda: processor
    fastapi_app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        yield fastapi_app
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def cashier_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    from .factories import register

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        await register(http_client, email="cashier@test.com")
        yield http_client


@pytest_asyncio.fixture
async def admin_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    from .factories import ADMIN_EMAIL, register

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        await register(
            http_client, email=ADMIN_EMAIL, first_name="Admin", last_name="User"
        )
        yield http_client
