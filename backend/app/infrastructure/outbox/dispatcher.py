# backend/app/infrastructure/outbox/dispatcher.py

from __future__ import annotations

from .contracts import OutboxHandlerRegistry


# AGENT: TODO
class OutboxDispatcher:
    def __init__(
        self,
        registry: OutboxHandlerRegistry,
        *,
        max_attempts: int = 10,
        batch_size: int = 1,
        poll_interval_s: int = 1,
        claim_ttl_s: int = 30,
        backoff_base_s: int = 5,
        backoff_cap_s: int = 900,
    ): ...

    async def start(self) -> None: ...

    async def end(self) -> None: ...

    async def tick(self) -> None: ...


__all__ = [
    "OutboxDispatcher",
]
