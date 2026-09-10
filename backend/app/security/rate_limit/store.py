"""Redis counters for fixed-window rate limiting.

- ``rate_limit:{scope}:{identifier}`` is a server-atomic counter of hits
  within the current window. The window is fixed and anchored at the first
  hit: INCR is atomic on the server, so the count is exact under concurrent
  requests — no read-modify-write race can undercount.
- ``EXPIRE NX`` both arms the window on the first hit and heals an orphaned
  counter left behind by a crash between the INCR and the EXPIRE — the next
  hit simply starts a fresh window on the surviving key.
- The key's TTL is what callers surface as ``Retry-After``: it is exactly the
  time until the window resets and the counter disappears.
- Known artifact of fixed windows: a burst straddling a window boundary can
  pass up to twice the limit across the two adjacent windows. That is
  acceptable for abuse control, which caps sustained rates rather than
  guaranteeing a hard per-instant ceiling.
"""

from __future__ import annotations

from datetime import timedelta
from typing import NamedTuple

from app.infrastructure.redis import Redis


def _rate_limit_key(scope: str, identifier: str) -> str:
    return f"rate_limit:{scope}:{identifier}"


class RateLimitHit(NamedTuple):
    # The field intentionally shadows tuple.count, which the NamedTuple never
    # uses as a method.
    count: int  # pyright: ignore[reportIncompatibleMethodOverride]
    retry_after_seconds: int


async def count_hit(
    redis: Redis, *, scope: str, identifier: str, window: timedelta
) -> RateLimitHit:
    """Atomically record a hit; returns its 1-based count and the reset delay.

    A non-positive TTL means the reply raced the key's expiry (or the EXPIRE
    itself); the full window is reported instead, which at worst overstates
    the wait.
    """
    key = _rate_limit_key(scope, identifier)
    count = await redis.incr(key)
    await redis.expire(key, window, nx=True)  # pyright: ignore[reportUnknownMemberType]
    ttl = int(await redis.ttl(key))

    retry_after = int(window.total_seconds()) if ttl <= 0 else ttl

    return RateLimitHit(count=int(count), retry_after_seconds=retry_after)


__all__ = ["RateLimitHit", "count_hit"]
