# backend/tests/integration/test_redis.py

"""Plumbing test: the Redis container fixture, client, and cleaner work."""

from __future__ import annotations

from redis.asyncio import Redis


async def test_set_get_expire_round_trip(redis_client: Redis) -> None:
    await redis_client.set("plumbing:key", "value")
    assert await redis_client.get("plumbing:key") == "value"

    await redis_client.expire("plumbing:key", 60)
    ttl = await redis_client.ttl("plumbing:key")
    assert 0 < ttl <= 60
