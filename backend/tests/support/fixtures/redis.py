# backend/tests/support/fixtures/redis.py

"""Redis fixtures: throwaway Redis, per-test FLUSHDB.

Provisioning is lazy: nothing Redis-related happens until a test
(transitively) requests `redis_client`. The autouse `clean_redis` fixture
consults `_redis_state` and no-ops for tests that never touched Redis —
this is what lets the unit tier run without Docker.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from redis import Redis as SyncRedis
from redis.asyncio import Redis


@dataclass
class ProvisionedRedis:
    """Session-wide record of whether (and where) a test Redis exists."""

    url: str | None = None


@pytest.fixture(scope="session")
def _redis_state() -> ProvisionedRedis:  # pyright: ignore[reportUnusedFunction]
    # Consumed by the redis_url and clean_redis fixtures via name injection,
    # which pyright does not count as a reference.
    return ProvisionedRedis()


@pytest.fixture(scope="session")
def redis_url(_redis_state: ProvisionedRedis) -> Iterator[str]:
    """A Redis to test against: TEST_REDIS_URL, or a throwaway container."""
    if url := os.environ.get("TEST_REDIS_URL"):
        _redis_state.url = url
        yield url
        return

    from testcontainers.redis import (  # pyright: ignore[reportMissingTypeStubs]
        RedisContainer,
    )

    with RedisContainer("redis:8") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        url = f"redis://{host}:{port}/0"
        _redis_state.url = url
        yield url


@pytest.fixture(autouse=True)
def clean_redis(_redis_state: ProvisionedRedis) -> Iterator[None]:
    yield
    if _redis_state.url is None:  # this test never provisioned Redis
        return
    # Cleanup uses a sync client to stay off any test event loop.
    client = SyncRedis.from_url(_redis_state.url)  # pyright: ignore[reportUnknownMemberType]
    try:
        client.flushdb()  # pyright: ignore[reportUnknownMemberType]
    finally:
        client.close()


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        redis_url, decode_responses=True
    )
    try:
        yield client
    finally:
        await client.aclose()


async def redis_keys(client: Redis, pattern: str) -> list[str]:
    """Typed KEYS wrapper for assertions (redis-py's `keys` is partially untyped)."""
    keys = await client.keys(pattern)  # pyright: ignore[reportUnknownMemberType]
    return [str(key) for key in keys]
