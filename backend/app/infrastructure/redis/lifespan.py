# backend/app/infrastructure/redis/lifespan.py

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.core.config import settings


@asynccontextmanager
async def redis_lifespan() -> AsyncGenerator[Redis]:
    """Build the Redis client and verify connectivity; close the client on exit."""
    client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        settings.redis.URL, decode_responses=True
    )
    try:
        # Fail fast on an unreachable or misconfigured Redis.
        await client.ping()  # pyright: ignore[reportUnknownMemberType]
        yield client
    finally:
        await client.aclose()
