from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


@asynccontextmanager
async def time_floor(ms: int) -> AsyncGenerator[None]:
    """Pad the wrapped block to a minimum duration.

    A timing-attack mitigation: when a block does observably different
    amounts of work for different inputs (an account lookup that hits vs
    misses), padding every outcome to a shared floor keeps the response
    time from revealing which path ran. The floor must sit above the slow
    path's tail latency — padding only stretches responses faster than the
    floor, so a tail that exceeds it still leaks.

    Padding also applies when the block raises (the point: error responses
    must take as long as successes), and the exception propagates after
    the sleep. 0 disables the floor naturally (remaining <= 0 -> no
    sleep). The sleep yields the event loop; no thread is held.
    """
    start = time.monotonic()
    try:
        yield
    finally:
        remaining = ms / 1000 - (time.monotonic() - start)
        if remaining > 0:
            await asyncio.sleep(remaining)


__all__ = ["time_floor"]
